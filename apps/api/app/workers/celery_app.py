"""Shared Celery application instance.

Runs as a separate Railway service. Start with:
    celery -A app.workers.celery_app worker --loglevel=info
"""

from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "jobnok",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.modules.bulk_email.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,             # Acknowledge after completion, not on receipt
    worker_prefetch_multiplier=1,    # Process one task at a time per worker
)
