"""Shared ARQ worker configuration.

Runs as a separate service (same image as the API, different start command):
    arq app.workers.arq_worker.WorkerSettings
"""

from arq import cron
from arq.connections import ArqRedis, RedisSettings
from fastapi import Request

from app.core.config import settings
from app.core.logging import setup_logging
from app.shared import model_registry  # noqa: F401 — registers every table on Base.metadata.
# The worker runs as its own process (see module docstring below), separate
# from the FastAPI app - it never imports app/main.py, so without this any
# task whose ORM operations need cross-module FK resolution (e.g.
# StartupHuntSource.user_id -> profiles.id) fails with NoReferencedTableError
# the moment SQLAlchemy configures mappers, since `profiles`' model class was
# never imported anywhere in this process. Same reason alembic/env.py imports
# this too - see model_registry.py's own docstring.
from app.modules.bulk_email.tasks import send_campaign_email, sweep_stuck_email_sends
from app.modules.job_search.tasks import sweep_expired_jobs
from app.modules.startup_hunt.tasks import resolve_startup_hunt_source_task
from app.modules.startup_hunt.ingestion.scheduler import dispatch_due_companies, sweep_stuck_resolutions
from app.modules.startup_hunt.workers.discovery_worker import run_discovery
from app.modules.startup_hunt.workers.resolution_worker import resolve_company_task
from app.modules.startup_hunt.workers.sync_worker import sync_company_task

# app/main.py calls this for the FastAPI process; this worker runs as its own
# separate process (see module docstring above) and never imports main.py, so
# without this call here too, Sentry was never initialized for it at all -
# any unhandled exception in a task (a plain Exception, not an arq.Retry) is
# just logged via logger.exception() and otherwise vanishes (keep_result=0
# below means arq doesn't even keep a trace of it). Sentry's logging
# integration is on by default, so this alone is enough to start capturing
# those - no per-task changes needed.
setup_logging(settings)


def get_arq_pool(request: Request) -> ArqRedis:
    """FastAPI dependency yielding the shared ARQ connection pool.

    The pool is created once at app startup (see app/main.py's lifespan)
    and reused across requests — same lifecycle as the async DB engine.
    """
    return request.app.state.arq_pool


class WorkerSettings:
    functions = [
        send_campaign_email,
        sweep_stuck_email_sends,
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
    #
    # Discovery runs 8x/day (every 3h) rather than the safer-feeling 6x -
    # chosen deliberately for faster initial coverage of the ~4,500 listed
    # startups (see startup_hunt_discovery_batch_size's comment for the
    # math), and per-run timing has enough margin (measured ~12s vs. the 30s
    # job_timeout) that neither frequency choice was ever the risk. No need
    # to speed up resolution/sync in lockstep - resolution is event-driven
    # (enqueued immediately per discovered company) and drains a batch of
    # 50 well within the 3h gap before the next discovery run; sync's own
    # 15-min dispatch tick already paces independently of discovery's pace.
    cron_jobs = [
        cron(run_discovery, hour={0, 3, 6, 9, 12, 15, 18, 21}, minute=0),
        cron(dispatch_due_companies, minute={0, 15, 30, 45}),
        # Catches companies stuck in 'resolving' by a crashed/killed
        # resolve_company_task - see scheduler.py's docstring for why ARQ's
        # own retry mechanism doesn't cover this on its own.
        cron(sweep_stuck_resolutions, minute={0, 30}),
        # Same class of gap, for bulk email sends - see
        # bulk_email/tasks.py::sweep_stuck_email_sends's docstring.
        cron(sweep_stuck_email_sends, minute={0, 10, 20, 30, 40, 50}),
        # Table hygiene, not correctness (every read already filters expired
        # rows out) - once a day at a quiet hour is plenty.
        cron(sweep_expired_jobs, hour={3}, minute=0),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10       # concurrent jobs this worker process runs; Resend pacing is
                         # enforced separately by the token bucket in rate_limiter.py
    max_tries = 4        # initial attempt + 3 retries
    job_timeout = 30     # seconds — a single Resend API call should never take this long
    keep_result = 0      # job status lives in EmailRecipient.status, not arq's result store
