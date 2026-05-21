"""
Health-check router for Lumenis AI.

Pings every backing service (PostgreSQL, Redis, Qdrant) and returns
aggregate health status.
"""

from __future__ import annotations

import logging

import redis
from fastapi import APIRouter, Depends
from qdrant_client import QdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


async def _check_db(db: AsyncSession) -> bool:
    """Return True if the database is reachable."""
    try:
        await db.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database health-check failed: %s", exc)
        return False


def _check_redis() -> bool:
    """Return True if Redis is reachable."""
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=3)
        return r.ping()
    except Exception as exc:
        logger.warning("Redis health-check failed: %s", exc)
        return False


def _check_qdrant() -> bool:
    """Return True if Qdrant is reachable."""
    try:
        client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT, timeout=3)
        # get_collections is a lightweight RPC call
        client.get_collections()
        return True
    except Exception as exc:
        logger.warning("Qdrant health-check failed: %s", exc)
        return False


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Aggregate health endpoint.

    Returns the status of each backing service and the overall API version.
    """
    db_ok = await _check_db(db)
    redis_ok = _check_redis()
    qdrant_ok = _check_qdrant()

    all_healthy = db_ok and redis_ok and qdrant_ok

    return {
        "status": "ok" if all_healthy else "degraded",
        "version": "0.1.0",
        "services": {
            "db": db_ok,
            "redis": redis_ok,
            "qdrant": qdrant_ok,
        },
    }
