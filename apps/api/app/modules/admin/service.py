"""Read-only crawler observability queries for the admin app (Tier 1 -
dashboard visibility only, no writes). Reads directly off company_registry
and the shared jobs table - no new tables, this module owns no state of its
own.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.shared.utils import row_to_dict
from app.modules.job_search.models import Job
from app.modules.startup_hunt.models import CompanyRegistry

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50

# Mirrors CompanyRegistry's own CHECK constraint (models.py) - kept here too
# so an invalid ?status= filter fails fast with a clear 422 instead of
# silently matching zero rows.
_VALID_STATUSES = {
    "discovered", "resolving", "resolved", "active",
    "no_careers_page", "no_jobs", "failed", "disabled",
}


async def get_crawler_overview(db: AsyncSession) -> dict:
    status_rows = (
        await db.execute(select(CompanyRegistry.status, func.count()).group_by(CompanyRegistry.status))
    ).all()
    status_counts = {status: count for status, count in status_rows}
    total_companies = sum(status_counts.values())

    unhealthy_count = await db.scalar(
        select(func.count()).select_from(CompanyRegistry).where(CompanyRegistry.consecutive_failures > 0)
    ) or 0

    overdue_sync_count = await db.scalar(
        select(func.count())
        .select_from(CompanyRegistry)
        .where(
            CompanyRegistry.status == "active",
            CompanyRegistry.next_crawl_at.isnot(None),
            CompanyRegistry.next_crawl_at < datetime.now(timezone.utc),
        )
    ) or 0

    total_crawler_jobs = await db.scalar(
        select(func.count()).select_from(Job).where(Job.company_id.isnot(None))
    ) or 0

    last_discovered_at = await db.scalar(select(func.max(CompanyRegistry.last_discovered_at)))
    last_synced_at = await db.scalar(select(func.max(CompanyRegistry.last_synced_at)))

    return {
        "status_counts": status_counts,
        "total_companies": total_companies,
        "unhealthy_count": unhealthy_count,
        "overdue_sync_count": overdue_sync_count,
        "total_crawler_jobs": total_crawler_jobs,
        "last_discovered_at": last_discovered_at,
        "last_synced_at": last_synced_at,
        # Config visibility, not just DB state - "why is nothing being
        # discovered" is answered right here instead of requiring someone to
        # go check .env separately.
        "discovery_enabled": settings.startup_hunt_startupmap_enabled,
        "discovery_batch_size": settings.startup_hunt_discovery_batch_size,
        "sync_batch_size": settings.startup_hunt_sync_batch_size,
    }


async def list_companies(
    db: AsyncSession,
    *,
    status: str | None = None,
    search: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> dict:
    if status is not None and status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status filter: {status!r}")

    conditions = []
    if status:
        conditions.append(CompanyRegistry.status == status)
    if search:
        term = f"%{search.strip()}%"
        conditions.append(or_(CompanyRegistry.name.ilike(term), CompanyRegistry.domain.ilike(term)))

    page_size = min(max(limit, 1), MAX_PAGE_SIZE)

    total = await db.scalar(select(func.count()).select_from(CompanyRegistry).where(*conditions)) or 0
    rows = (
        await db.execute(
            select(CompanyRegistry)
            .where(*conditions)
            .order_by(CompanyRegistry.updated_at.desc())
            .limit(page_size)
            .offset(max(offset, 0))
        )
    ).scalars().all()

    return {"total": total, "items": [row_to_dict(r) for r in rows]}


async def get_company_detail(db: AsyncSession, company_id: str) -> dict:
    company = await db.get(CompanyRegistry, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    jobs = (
        await db.execute(
            select(Job).where(Job.company_id == company_id).order_by(Job.last_seen_at.desc()).limit(100)
        )
    ).scalars().all()

    return {
        "company": row_to_dict(company),
        "jobs": [row_to_dict(j) for j in jobs],
        "job_count": len(jobs),
    }
