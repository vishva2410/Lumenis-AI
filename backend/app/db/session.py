"""
Lumenis AI — Async Database Session Management

Sets up the async SQLAlchemy engine, session factory,
and provides a FastAPI-compatible dependency (`get_db`).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base

# ── Async Engine (for FastAPI) ─────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

# ── Async Session Factory ──────────────────────────────────────────
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# ── Sync Engine & Session (for Celery workers) ─────────────────────
sync_engine = create_engine(
    settings.database_url_sync,
    echo=False,
    future=True,
    pool_size=5,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
)


# ── FastAPI Dependency ─────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an async database session.

    Usage in a FastAPI route::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Bootstrap ──────────────────────────────────────────────────────
async def init_db() -> None:
    """
    Create all tables defined by models that inherit from ``Base``.

    Call this once during application startup (e.g., in a lifespan handler).
    In production, prefer Alembic migrations instead.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
