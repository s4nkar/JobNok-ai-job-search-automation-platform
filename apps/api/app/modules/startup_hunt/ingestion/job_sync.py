"""Pulls current jobs for one resolved company (Pipeline C, PRD section 8.3)
and upserts them into the shared `jobs` cache - reuses the exact same ATS
provider fetch() functions the live search pipeline calls (see engine.py's
StartupHuntSourceConfig contract), never duplicates their scraping logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.cache import circuit_is_open, record_provider_result
from app.modules.job_search.service import _upsert_jobs_cache
from app.modules.startup_hunt.engine import StartupHuntSourceConfig
from app.modules.startup_hunt.ingestion import generic_crawler
from app.modules.startup_hunt.models import CompanyRegistry
from app.modules.startup_hunt.providers import ashby, greenhouse, lever
from app.modules.startup_hunt.service import _opportunity_to_job_cache_row

logger = logging.getLogger(__name__)

_ATS_FETCHERS = {"ashby": ashby.fetch, "greenhouse": greenhouse.fetch, "lever": lever.fetch}


@dataclass
class SyncResult:
    ok: bool
    job_count: int
    error: str | None = None


async def _fetch_opportunities(company: CompanyRegistry) -> list[dict]:
    if company.ats_provider == "generic":
        return await generic_crawler.fetch(company)

    fetcher = _ATS_FETCHERS.get(company.ats_provider or "")
    if fetcher is None:
        raise ValueError(f"Unsupported ats_provider: {company.ats_provider}")

    if await circuit_is_open("startup_hunt", company.ats_provider):
        raise RuntimeError(f"{company.ats_provider} circuit open - skipping this cycle")

    source = StartupHuntSourceConfig(
        type=company.ats_provider,
        name=company.name,
        company=company.name,
        slug=company.ats_identifier,
        url=company.career_url,
        metadata={
            "country": company.country,
            "city": company.city,
            "company_website_url": company.website_url,
            "careers_url": company.career_url,
        },
    )
    async with httpx.AsyncClient(timeout=settings.startup_hunt_timeout_seconds) as client:
        opportunities = await fetcher(client, source)
    await record_provider_result("startup_hunt", company.ats_provider, ok=True)
    return opportunities


async def sync_company(db: AsyncSession, company: CompanyRegistry) -> SyncResult:
    if not company.ats_provider:
        return SyncResult(ok=False, job_count=0, error="Company has no resolved ats_provider")

    try:
        opportunities = await _fetch_opportunities(company)
    except Exception as exc:
        if company.ats_provider != "generic":
            await record_provider_result("startup_hunt", company.ats_provider, ok=False)
        logger.warning("Sync failed for company %s (%s): %s", company.name, company.ats_provider, exc)
        return SyncResult(ok=False, job_count=0, error=str(exc))

    # Dedupe on (provider_type, external_job_id) before upserting - the same
    # (source, source_job_id) key appearing twice in one batch makes Postgres
    # reject the whole INSERT ... ON CONFLICT statement ("cannot affect row a
    # second time"), and a single ATS board can legitimately list the same
    # canonical URL more than once (e.g. one role cross-posted to multiple
    # departments/locations). Mirrors service.py's fresh_cacheable_rows_by_key
    # handling of the exact same problem for the live search path.
    rows_by_key: dict[tuple[str, str], dict] = {}
    for item in opportunities:
        row = _opportunity_to_job_cache_row(item)
        if row is not None:
            rows_by_key[(row["provider_type"], row["external_job_id"])] = row
    rows = list(rows_by_key.values())

    if rows:
        ttl_hours = max(2 * company.crawl_frequency_hours, 48)
        await _upsert_jobs_cache(
            db, rows, origin_tool="startup_hunt", ttl_hours=ttl_hours, company_id=company.id
        )

    return SyncResult(ok=True, job_count=len(rows))
