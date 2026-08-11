"""Shared ARQ worker configuration.

Runs as a separate service (same image as the API, different start command):
    arq app.workers.arq_worker.WorkerSettings
"""

from arq.connections import ArqRedis, RedisSettings
from fastapi import Request

from app.core.config import settings
from app.modules.bulk_email.tasks import send_campaign_email


def get_arq_pool(request: Request) -> ArqRedis:
    """FastAPI dependency yielding the shared ARQ connection pool.

    The pool is created once at app startup (see app/main.py's lifespan)
    and reused across requests — same lifecycle as the async DB engine.
    """
    return request.app.state.arq_pool


class WorkerSettings:
    functions = [send_campaign_email]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10       # concurrent jobs this worker process runs; Resend pacing is
                         # enforced separately by the token bucket in rate_limiter.py
    max_tries = 4        # initial attempt + 3 retries
    job_timeout = 30     # seconds — a single Resend API call should never take this long
    keep_result = 0      # job status lives in EmailRecipient.status, not arq's result store
