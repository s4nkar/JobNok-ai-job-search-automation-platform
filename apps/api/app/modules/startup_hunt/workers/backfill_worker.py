"""ARQ task: one-off backfill of funding_stage/employee_count_min/max/
description for company_registry rows discovered before those columns
existed (migrations e64a6643c9a0, 826d16204c5f). Deliberately NOT in
arq_worker.py's cron_jobs - manually enqueued once after each such migration
ships, and safe to re-run since it only ever selects rows still missing
description (an accidental second run is a no-op, not a duplicate-work
problem).

Selection is keyed on `description IS NULL` alone, not all three fields -
description was added after funding_stage/employee_count_min/max, so most
rows already have those two filled from the previous run of this same task
and only need this one field. Re-fetching still re-extracts all three from
the live page regardless (cheap, same request either way) - upsert_discovered
's COALESCE means that's a harmless no-op for whichever fields a row already
has, see discovery_service.py.

Scoped to discovery_source='startupmap' only - those rows have a reliable,
single-format URL to re-fetch (their own discovery_source_url, the exact
page StartupMapSource itself already knows how to parse). startup_scout-
sourced rows point at Crunchbase/Wellfound/Dealroom profile pages instead;
directly re-fetching those crosses the line this session's own legal-risk
assessment drew (DDG-mediated access is low-risk, a bot hitting those sites'
own servers directly is the higher-risk category that assessment avoided) -
those rows are left to fill in naturally the next time startup_scout
re-discovers the same company.

For a company whose StartupMap page itself has neither numberOfEmployees
nor a stage keyword (confirmed live: ~4% of a real run), falls back to a
DDG search of the company name - same DDG-mediated, zero-additional-cost
approach startup_scout's own discovery already relies on, see
_ddg_fallback_stage_and_size below.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.startup_hunt.discovery import discovery_service
from app.modules.startup_hunt.discovery.startupmap import _fetch_one
from app.modules.startup_hunt.discovery.startup_source import DiscoveredStartup
from app.modules.startup_hunt.models import CompanyRegistry
from app.modules.startup_scout.engine import _ddg_search_raw
from app.services.cache import circuit_is_open, record_provider_result
from app.shared import funding_stages

logger = logging.getLogger(__name__)


async def _ddg_fallback_stage_and_size(
    company_name: str, domain: str | None
) -> tuple[str | None, int | None, int | None]:
    """DDG search fallback for a company StartupMap itself has no
    numberOfEmployees/keywords data for. DDG-mediated, never a direct fetch
    of a third-party site - the same low-risk category startup_scout's own
    discovery already relies on (see its engine.py module docstring).
    Reuses the shared circuit breaker startup_scout's own live search uses
    ("startup_scout"/"ddg" scope) so this and regular searches back off
    together if DDG starts hard-failing, rather than each tracking it
    separately. Best-effort throughout - any failure just means no
    stage/size found for this company, never raised.

    Anchors the query on the company's own domain when known, not just its
    name - verified live that a name-only query for a small/generic-named
    company ("Mana Break") returned unrelated results for a same-named video
    game, while anchoring on its actual domain correctly surfaced the real
    company (found "seed" for a different test company this way that the
    name-only query missed entirely).
    """
    if await circuit_is_open("startup_scout", "ddg"):
        return None, None, None
    query = f"{domain} funding stage employees team size" if domain else f'"{company_name}" funding stage employees team size'
    try:
        results = await _ddg_search_raw(query, max_results=8)
        await record_provider_result("startup_scout", "ddg", ok=True)
    except Exception:
        await record_provider_result("startup_scout", "ddg", ok=False)
        return None, None, None

    combined = " ".join(f"{r.get('title', '')} {r.get('body', '')}" for r in results)
    stage = funding_stages.detect_stage(combined)
    emp_min, emp_max = funding_stages.detect_employee_range(combined)
    return stage, emp_min, emp_max


async def _fill_gaps_with_ddg(items: list[DiscoveredStartup]) -> int:
    """Mutates `items` in place - only attempts a DDG lookup for rows
    StartupMap's own structured data left completely empty on both fields
    (not just one), and only one company at a time (sequential, with a
    pause between each) rather than concurrently - this is a fallback for a
    handful of gaps, not a bulk operation, so there's no need for the same
    concurrency/chunking startupmap.one's own fetch uses. Returns how many
    it actually found something for, so the caller can report a real
    StartupMap-vs-DDG breakdown instead of one combined number."""
    filled = 0
    for item in items:
        if item.funding_stage is not None or item.employee_count_min is not None:
            continue
        stage, emp_min, emp_max = await _ddg_fallback_stage_and_size(item.name, item.domain)
        item.funding_stage = stage
        item.employee_count_min = emp_min
        item.employee_count_max = emp_max
        if stage is not None or emp_min is not None:
            filled += 1
        await asyncio.sleep(1.0)
    return filled


async def backfill_company_metadata(ctx: dict) -> None:
    async with AsyncSessionLocal() as db:
        slugs = (
            await db.execute(
                select(CompanyRegistry.discovery_source_id).where(
                    CompanyRegistry.discovery_source == "startupmap",
                    CompanyRegistry.description.is_(None),
                    CompanyRegistry.discovery_source_id.isnot(None),
                )
            )
        ).scalars().all()

    if not slugs:
        logger.info(
            "backfill_company_metadata: nothing to do - every startupmap-sourced company "
            "already has a description."
        )
        return

    # Chunked, not one asyncio.gather() over every slug - a first real run
    # (822 slugs) fired the whole batch in one burst and got hit with
    # widespread 429s from startupmap.one (516 of ~800 requests), even
    # though each chunk only ever runs startup_hunt_startupmap_fetch_
    # concurrency requests concurrently. That setting bounds *in-flight*
    # requests, not *total volume over time* - ongoing discovery only ever
    # fetches startup_hunt_discovery_batch_size (50) pages per run, so it
    # never actually exercises this path; a one-off backfill of hundreds of
    # rows is a fundamentally different traffic shape. Chunking to the same
    # size as a normal discovery run, with a real pause between chunks,
    # makes this look like several ordinary discovery runs back to back
    # instead of one 16x-oversized burst.
    chunk_size = settings.startup_hunt_discovery_batch_size
    semaphore = asyncio.Semaphore(settings.startup_hunt_startupmap_fetch_concurrency)
    total_chunks = -(-len(slugs) // chunk_size)  # ceiling division
    discovered = []
    ddg_filled_total = 0
    still_empty_total = 0
    description_filled_total = 0
    for i in range(0, len(slugs), chunk_size):
        chunk = slugs[i : i + chunk_size]
        results = await asyncio.gather(*(_fetch_one(slug, semaphore) for slug in chunk))
        chunk_discovered = [r for r in results if r is not None]
        fetch_failed = len(chunk) - len(chunk_discovered)
        description_filled = sum(1 for c in chunk_discovered if c.description is not None)
        description_filled_total += description_filled

        # DDG fallback for whatever StartupMap itself still left empty on
        # funding_stage/employee_count - zero additional cost, DDG-mediated
        # (see _ddg_fallback_stage_and_size docstring). DDG snippets don't
        # carry a usable description, so this fallback never touches that
        # field - a row whose StartupMap page itself has no description text
        # just stays without one. Applied before the upsert below so a
        # filled-in gap is saved in the same commit as everything else from
        # this chunk.
        ddg_filled = await _fill_gaps_with_ddg(chunk_discovered)
        ddg_filled_total += ddg_filled
        still_empty = sum(1 for c in chunk_discovered if c.funding_stage is None and c.employee_count_min is None)
        still_empty_total += still_empty

        discovered.extend(chunk_discovered)

        if chunk_discovered:
            async with AsyncSessionLocal() as db:
                # upsert_discovered's COALESCE-on-conflict (see
                # discovery_service.py) means this only ever fills in a
                # still-missing value, never blanks out something a normal
                # discovery cycle found in the meantime. Committed per chunk,
                # not once at the end, so a later chunk hitting the job
                # timeout doesn't lose earlier chunks' progress.
                await discovery_service.upsert_discovered(db, chunk_discovered)
                await db.commit()

        logger.info(
            "backfill_company_metadata: chunk %d/%d - %d/%d pages fetched (%d failed), "
            "%d got a description, %d filled by the DDG fallback, %d still have no funding_stage/"
            "employee_count after both attempts",
            i // chunk_size + 1, total_chunks, len(chunk_discovered), len(chunk), fetch_failed,
            description_filled, ddg_filled, still_empty,
        )

        if i + chunk_size < len(slugs):
            await asyncio.sleep(settings.startup_hunt_backfill_chunk_delay_seconds)

    startupmap_direct_total = len(discovered) - ddg_filled_total - still_empty_total
    description_missing_total = len(discovered) - description_filled_total
    logger.info(
        "backfill_company_metadata: done - %d row(s) needed data, %d got a description, %d have "
        "no description (their source page genuinely doesn't have one). funding_stage/"
        "employee_count: %d successfully re-fetched from StartupMap directly, %d more filled by "
        "the DDG fallback, %d still empty after both attempts (re-running won't change that until "
        "StartupMap's own listing is updated).",
        len(slugs), description_filled_total, description_missing_total,
        startupmap_direct_total, ddg_filled_total, still_empty_total,
    )
