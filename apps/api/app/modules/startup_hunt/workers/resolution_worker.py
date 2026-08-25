"""ARQ task: resolves one company_registry row's ATS/careers source (Pipeline
B) and, on success, promotes it into the ongoing sync rotation. See
ingestion/ats_resolver.py for the actual resolution logic - this file only
owns the state transitions and enqueueing around it (mirrors the split
between resolver.py and tasks.py's resolve_startup_hunt_source_task for the
"My Sources" flow).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.database import AsyncSessionLocal
from app.modules.startup_hunt.ingestion import ats_resolver
from app.modules.startup_hunt.models import CompanyRegistry

logger = logging.getLogger(__name__)


async def resolve_company_task(ctx: dict, company_id: str) -> None:
    async with AsyncSessionLocal() as db:
        company = await db.get(CompanyRegistry, company_id)
        if company is None or company.status not in ("discovered", "resolving", "failed"):
            return  # already resolved/disabled/deleted through another path

        company.status = "resolving"
        await db.flush()

        await ats_resolver.resolve_company(company)

        promoted = company.status == "resolved"
        if promoted:
            # 'resolved' is a momentary state - a company with a known
            # source is immediately eligible for the ongoing sync rotation,
            # not held back for a separate manual promotion step.
            company.status = "active"
            company.next_crawl_at = datetime.now(timezone.utc)
            # Clears any count built up by the stuck-resolution sweep (see
            # scheduler.py::sweep_stuck_resolutions) before this company
            # enters the sync rotation, so a rough resolution doesn't eat
            # into sync's own failure budget on the same field.
            company.consecutive_failures = 0

        await db.commit()

    if promoted:
        # Uses the company_id parameter, not company.id - expire_on_commit
        # (SQLAlchemy's default) would turn a post-commit attribute access on
        # `company` into a lazy-load against an already-closed session.
        await ctx["redis"].enqueue_job("sync_company_task", company_id=company_id)
