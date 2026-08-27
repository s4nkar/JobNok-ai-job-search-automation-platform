"""Manually enqueue any ARQ task by name - for tasks meant to be triggered
by hand (e.g. backfill_company_metadata, a one-off not on arq_worker.py's
cron_jobs), not tasks the app itself enqueues programmatically.

Run (from the host, matching promote_admin.py's own invocation style):

    docker compose exec api python -m app.scripts.enqueue_job <task_name>

The named task must be one of WorkerSettings.functions
(app/workers/arq_worker.py) - this just pushes a job onto the same Redis
queue the running `worker` container is already polling, it doesn't run
anything itself.
"""

from __future__ import annotations

import asyncio
import sys

from arq.connections import RedisSettings, create_pool

from app.core.config import settings


async def main(job_name: str) -> None:
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        job = await redis.enqueue_job(job_name)
        if job is None:
            print(
                f"Could not enqueue {job_name!r} - a job with the same ID may already be "
                "queued or running (ARQ dedupes by default job ID unless the task itself "
                "customizes it)."
            )
            raise SystemExit(1)
        print(f"Enqueued {job_name!r} as job {job.job_id} - watch `docker compose logs worker -f` for its result.")
    finally:
        await redis.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.scripts.enqueue_job <task_name>", file=sys.stderr)
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1]))
