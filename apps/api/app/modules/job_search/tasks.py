"""ARQ task: periodic cleanup of expired rows in the shared jobs cache.

Applies to the whole table, not just startup_hunt's crawler-synced rows -
job_search's own Adzuna/Bundesagentur listings share the exact same
expires_at/TTL mechanism (see models.py's Job model), so one cleanup task
serves both.

Every read already filters out expired rows (query_job_cache_candidates,
_fetch_db_candidates, etc. all use `WHERE expires_at > now()`), so this
isn't required for query correctness - it's table hygiene, keeping `jobs`
from growing unboundedly with rows nothing will ever read again.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.modules.job_search.models import Job

logger = logging.getLogger(__name__)


async def sweep_expired_jobs(ctx: dict) -> None:
    """ARQ cron entrypoint (see arq_worker.py's cron_jobs)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(delete(Job).where(Job.expires_at < datetime.now(timezone.utc)))
        deleted = result.rowcount
        await db.commit()
    if deleted:
        logger.info("Deleted %d expired job(s) from the shared jobs cache", deleted)
