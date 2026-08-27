"""Sync scheduler (PRD sections 23, 26) - the ARQ cron entrypoint that keeps
sync continuous instead of one giant daily batch: each tick picks a small,
priority-ordered batch of companies whose next_crawl_at has arrived and hands
each one off to workers.sync_worker.sync_company_task individually, so one
slow or failing company's sync can never block the dispatch tick or any
other company's sync.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.startup_hunt.models import CompanyRegistry

logger = logging.getLogger(__name__)

_PRIORITY_ORDER = case(
    (CompanyRegistry.crawl_priority == "high", 0),
    (CompanyRegistry.crawl_priority == "normal", 1),
    else_=2,
)


async def select_due_companies(db: AsyncSession, limit: int) -> list[CompanyRegistry]:
    rows = (
        await db.execute(
            select(CompanyRegistry)
            .where(CompanyRegistry.status == "active", CompanyRegistry.next_crawl_at <= func.now())
            .order_by(_PRIORITY_ORDER, CompanyRegistry.next_crawl_at)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def dispatch_due_companies(ctx: dict) -> None:
    """ARQ cron entrypoint (see arq_worker.py's cron_jobs). Only enqueues -
    never runs a sync itself - so this tick returns immediately regardless
    of how long any individual company's sync takes."""
    async with AsyncSessionLocal() as db:
        companies = await select_due_companies(db, settings.startup_hunt_sync_batch_size)

    if not companies:
        return

    for company in companies:
        await ctx["redis"].enqueue_job("sync_company_task", company_id=str(company.id))
    logger.info("Dispatched %d due companies to the sync queue", len(companies))


async def select_stuck_resolutions(db: AsyncSession, limit: int) -> list[CompanyRegistry]:
    """Companies left in 'resolving' by a resolve_company_task that never
    finished - the worker process died, was killed mid-job, or hit an
    unexpected exception. ARQ's own max_tries does NOT cover this case: it
    only retries a job that explicitly raises arq.Retry, which
    resolve_company_task never does (see the conversation this was designed
    in) - a plain crash just leaves the row stuck with nothing watching it.
    This sweep is what actually finds and retries those.

    consecutive_failures caps it (startup_hunt_resolution_max_attempts) so a
    company that keeps crashing resolution doesn't get retried forever -
    reused from the same field sync failures use, reset to 0 by
    resolution_worker.py on a successful resolution so the two don't bleed
    into each other's budget.
    """
    stuck_cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=settings.startup_hunt_resolution_stuck_after_minutes
    )
    rows = (
        await db.execute(
            select(CompanyRegistry)
            .where(
                CompanyRegistry.status == "resolving",
                CompanyRegistry.updated_at < stuck_cutoff,
                CompanyRegistry.consecutive_failures < settings.startup_hunt_resolution_max_attempts,
            )
            .order_by(CompanyRegistry.updated_at)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def sweep_stuck_resolutions(ctx: dict) -> None:
    """ARQ cron entrypoint (see arq_worker.py's cron_jobs)."""
    async with AsyncSessionLocal() as db:
        stuck = await select_stuck_resolutions(db, settings.startup_hunt_resolution_sweep_batch_size)
        if not stuck:
            return
        ids = [company.id for company in stuck]
        # Bumping consecutive_failures also refreshes updated_at (trigger-
        # managed), which resets this row's staleness clock - if the retry
        # gets stuck again, it won't reappear in this query until another
        # full stuck_after_minutes window has passed.
        await db.execute(
            CompanyRegistry.__table__.update()
            .where(CompanyRegistry.id.in_(ids))
            .values(consecutive_failures=CompanyRegistry.consecutive_failures + 1)
        )
        await db.commit()

    for company_id in ids:
        await ctx["redis"].enqueue_job("resolve_company_task", company_id=str(company_id))
    logger.info("Re-enqueued %d stuck resolution(s)", len(ids))


async def select_undiscovered_companies(db: AsyncSession, limit: int) -> list[CompanyRegistry]:
    """Companies sitting at status='discovered' with no resolution enqueued
    for them yet - catches rows from ANY pipeline, not just
    discovery_worker.py's own StartupMap discoveries. That worker enqueues
    resolve_company_task inline, right after its own upsert, using the ARQ
    worker's ctx["redis"] - fine for a job already running inside an ARQ
    worker, but startup_scout's company_registry write-back
    (service.py::_store_discovered_companies) runs inside an HTTP request
    handler with no ARQ context to enqueue through directly. This sweep is
    what actually gets those rows resolved instead.

    The grace window (startup_hunt_discovery_sweep_after_minutes) exists so
    this never races a row's own just-committed insert, and doubles as
    protection against re-enqueueing a resolution that's already in flight:
    resolve_company_task flips status to 'resolving' before doing any real
    work (see resolution_worker.py), so once picked up once, a row simply
    stops matching this query on the next tick - no separate "already
    enqueued" bookkeeping needed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.startup_hunt_discovery_sweep_after_minutes)
    rows = (
        await db.execute(
            select(CompanyRegistry)
            .where(CompanyRegistry.status == "discovered", CompanyRegistry.last_discovered_at < cutoff)
            .order_by(CompanyRegistry.last_discovered_at)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def sweep_undiscovered_companies(ctx: dict) -> None:
    """ARQ cron entrypoint (see arq_worker.py's cron_jobs)."""
    async with AsyncSessionLocal() as db:
        undiscovered = await select_undiscovered_companies(db, settings.startup_hunt_discovery_sweep_batch_size)
    if not undiscovered:
        return

    for company in undiscovered:
        await ctx["redis"].enqueue_job("resolve_company_task", company_id=str(company.id))
    logger.info("Enqueued resolution for %d undiscovered company(ies)", len(undiscovered))
