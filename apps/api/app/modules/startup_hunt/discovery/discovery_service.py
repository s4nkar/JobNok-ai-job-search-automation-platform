"""Normalizes and upserts discovered startups into the global
company_registry - the write side of Pipeline A (PRD section 9). Domain is
the primary dedup key, falling back to (discovery_source,
discovery_source_id) when a startup has no resolvable domain yet - see
CompanyRegistry's partial unique indexes in models.py.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.startup_hunt.discovery.startup_source import DiscoveredStartup
from app.modules.startup_hunt.models import CompanyRegistry


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


async def upsert_discovered(db: AsyncSession, items: list[DiscoveredStartup]) -> list[str]:
    """Upserts a batch of discovered startups, returns the ids of rows that
    were newly inserted (not already-known companies) - callers use this to
    know which companies need resolution enqueued, so a re-discovery of an
    already-resolved company doesn't reset it back into the resolution queue.
    Bounded to startup_hunt_discovery_batch_size by the caller (discovery
    worker), not here - this function just writes whatever it's given.

    Dedup: domain first (ON CONFLICT on the partial unique domain index),
    falling back to (discovery_source, discovery_source_id) for startups
    with no domain yet. A startup with neither is inserted unconditionally -
    normalized_name alone isn't a safe automatic dedup key (too many
    false-positive collisions across unrelated companies sharing a common
    name), it only backs a manual/fallback lookup.

    New-vs-existing is detected via Postgres's `xmax = 0` trick on the
    RETURNING clause (true only for a row inserted by this exact command),
    not by comparing timestamps - both branches set last_discovered_at to
    `now` regardless of whether the row was just inserted or already existed,
    so a timestamp comparison can't tell them apart.
    """
    if not items:
        return []

    now = datetime.now(timezone.utc)
    new_ids: list[str] = []

    for item in items:
        base_fields = dict(
            name=item.name,
            normalized_name=_normalize_name(item.name),
            website_url=item.website_url,
            country=item.country,
            city=item.city,
            discovery_source=item.discovery_source,
            discovery_source_url=item.discovery_source_url,
            discovery_source_id=item.discovery_source_id,
            last_discovered_at=now,
        )

        if item.domain:
            stmt = pg_insert(CompanyRegistry).values(domain=item.domain, **base_fields)
            stmt = stmt.on_conflict_do_update(
                index_elements=["domain"],
                index_where=CompanyRegistry.domain.isnot(None),
                set_={"last_discovered_at": now},
            )
        elif item.discovery_source_id:
            stmt = pg_insert(CompanyRegistry).values(**base_fields)
            stmt = stmt.on_conflict_do_update(
                index_elements=["discovery_source", "discovery_source_id"],
                index_where=CompanyRegistry.discovery_source_id.isnot(None),
                set_={"last_discovered_at": now},
            )
        else:
            row = CompanyRegistry(**base_fields)
            db.add(row)
            await db.flush()
            new_ids.append(str(row.id))
            continue

        stmt = stmt.returning(CompanyRegistry.id, literal_column("(xmax = 0)").label("inserted"))
        result = (await db.execute(stmt)).first()
        if result is not None and result.inserted:
            new_ids.append(str(result.id))

    await db.flush()
    return new_ids
