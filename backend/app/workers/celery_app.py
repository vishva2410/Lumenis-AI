"""
Celery application factory for Lumenis AI.

Configures the Celery worker with Redis as broker and result backend,
JSON serialization, and sensible production defaults.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

# ── Create Celery app ────────────────────────────────────────────────
celery_app = Celery(
    "lumenis_ai",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# ── Configuration ────────────────────────────────────────────────────
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Reliability — ack only after the task completes, so a crashed
    # worker doesn't silently lose work.
    task_acks_late=True,
    # Fetch one task at a time per worker process to avoid starving
    # other workers when tasks have variable execution time.
    worker_prefetch_multiplier=1,
    # Result expiry — keep results for 24 hours
    result_expires=86400,
    # Don't store successful results by default (reduces Redis memory);
    # individual tasks can opt-in by setting `ignore_result = False`.
    task_ignore_result=False,
    # Retry on broker connection loss at startup
    broker_connection_retry_on_startup=True,
)

# ── Autodiscovery ────────────────────────────────────────────────────
# Automatically find @celery_app.task-decorated functions in these modules.
celery_app.autodiscover_tasks(["app.workers"])
