"""ARQ task: runs one discovery source, upserts companies into
company_registry, and enqueues resolution for every newly-discovered one.
See discovery/discovery_service.py for the dedupe/upsert logic itself.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.startup_hunt.discovery import discovery_service
from app.modules.startup_hunt.discovery.startupmap import StartupMapSource

logger = logging.getLogger(__name__)


async def run_discovery(ctx: dict) -> None:
    """ARQ cron entrypoint (see arq_worker.py's cron_jobs). A safe no-op
    while every discovery source is disabled - StartupMapSource.discover()
    itself checks startup_hunt_startupmap_enabled and returns [] when off
    (default), so this needs no separate gate here. Adding another discovery
    source later (PRD section 10) means running it here too, nothing else
    changes."""
    discovered = await StartupMapSource().discover()
    if not discovered:
        return

    discovered = discovered[: settings.startup_hunt_discovery_batch_size]
    async with AsyncSessionLocal() as db:
        new_ids = await discovery_service.upsert_discovered(db, discovered)
        await db.commit()

    logger.info("Discovery run: %d discovered, %d new companies", len(discovered), len(new_ids))
    for company_id in new_ids:
        await ctx["redis"].enqueue_job("resolve_company_task", company_id=company_id)
