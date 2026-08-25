"""Shared ARQ worker configuration.

Runs as a separate service (same image as the API, different start command):
    arq app.workers.arq_worker.WorkerSettings
"""

from arq import cron
from arq.connections import ArqRedis, RedisSettings
from fastapi import Request

from app.core.config import settings
from app.shared import model_registry  # noqa: F401 — registers every table on Base.metadata.
# The worker runs as its own process (see module docstring below), separate
# from the FastAPI app - it never imports app/main.py, so without this any
# task whose ORM operations need cross-module FK resolution (e.g.
# StartupHuntSource.user_id -> profiles.id) fails with NoReferencedTableError
# the moment SQLAlchemy configures mappers, since `profiles`' model class was
# never imported anywhere in this process. Same reason alembic/env.py imports
# this too - see model_registry.py's own docstring.
from app.modules.bulk_email.tasks import send_campaign_email
from app.modules.startup_hunt.tasks import resolve_startup_hunt_source_task
from app.modules.startup_hunt.ingestion.scheduler import dispatch_due_companies, sweep_stuck_resolutions
from app.modules.startup_hunt.workers.discovery_worker import run_discovery
from app.modules.startup_hunt.workers.resolution_worker import resolve_company_task
from app.modules.startup_hunt.workers.sync_worker import sync_company_task


def get_arq_pool(request: Request) -> ArqRedis:
    """FastAPI dependency yielding the shared ARQ connection pool.

    The pool is created once at app startup (see app/main.py's lifespan)
    and reused across requests — same lifecycle as the async DB engine.
    """
    return request.app.state.arq_pool


class WorkerSettings:
    functions = [
        send_campaign_email,
        resolve_startup_hunt_source_task,
        run_discovery,
        resolve_company_task,
        sync_company_task,
    ]
    # Startup Hunt's automated discovery/resolution/sync pipeline (see
    # modules/startup_hunt/discovery|ingestion|workers/) - this worker had no
    # cron_jobs at all before this. Discovery and resolution chain-enqueue
    # each other (see discovery_worker.py/resolution_worker.py); only the
    # sync dispatch needs to run on a fixed schedule.
    cron_jobs = [
        cron(run_discovery, hour={0, 6, 12, 18}, minute=0),
        cron(dispatch_due_companies, minute={0, 15, 30, 45}),
        # Catches companies stuck in 'resolving' by a crashed/killed
        # resolve_company_task - see scheduler.py's docstring for why ARQ's
        # own retry mechanism doesn't cover this on its own.
        cron(sweep_stuck_resolutions, minute={0, 30}),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10       # concurrent jobs this worker process runs; Resend pacing is
                         # enforced separately by the token bucket in rate_limiter.py
    max_tries = 4        # initial attempt + 3 retries
    job_timeout = 30     # seconds — a single Resend API call should never take this long
    keep_result = 0      # job status lives in EmailRecipient.status, not arq's result store
