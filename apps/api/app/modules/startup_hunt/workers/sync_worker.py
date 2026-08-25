"""ARQ task: syncs one company's jobs (Pipeline C) and updates its crawl
bookkeeping - last_synced_at/next_crawl_at/consecutive_failures/last_error.
See ingestion/job_sync.py for the actual fetch+upsert logic.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.core.database import AsyncSessionLocal
from app.modules.startup_hunt.ingestion import job_sync
from app.modules.startup_hunt.ingestion.backoff import backoff_hours
from app.modules.startup_hunt.models import CompanyRegistry

logger = logging.getLogger(__name__)


async def sync_company_task(ctx: dict, company_id: str) -> None:
    async with AsyncSessionLocal() as db:
        company = await db.get(CompanyRegistry, company_id)
        if company is None or company.status != "active":
            return  # disabled/deleted/not-yet-resolved through another path

        result = await job_sync.sync_company(db, company)
        now = datetime.now(timezone.utc)

        if result.ok:
            company.consecutive_failures = 0
            company.last_error = None
            company.last_synced_at = now
            company.next_crawl_at = now + timedelta(hours=company.crawl_frequency_hours)
            if result.job_count > 0:
                company.last_job_found_at = now
            # last_job_change_at is deliberately left unpopulated for MVP -
            # detecting an actual change (vs. just "still has jobs") needs a
            # before/after diff this pass doesn't do; reserved for the
            # adaptive-scheduling work in PRD Phase 5.
        else:
            company.consecutive_failures += 1
            company.last_error = (result.error or "")[:2000]
            company.next_crawl_at = now + timedelta(hours=backoff_hours(company.consecutive_failures))
            # Status stays 'active' even after repeated failures - still
            # under monitoring, just backing off. Returning a company to
            # source re-resolution after sustained failure (PRD section 34)
            # is a further refinement, not required for this pass.

        # Captured before commit - expire_on_commit (SQLAlchemy's default)
        # would otherwise turn any post-commit attribute access on `company`
        # into a lazy-load against an already-closed session.
        if not result.ok:
            log_name = company.name
            log_failures = company.consecutive_failures
            log_next_retry_hours = backoff_hours(company.consecutive_failures)

        await db.commit()

    if not result.ok:
        logger.warning(
            "Sync failed for company %s: %s (consecutive_failures=%d, next retry in %dh)",
            log_name, result.error, log_failures, log_next_retry_hours,
        )
