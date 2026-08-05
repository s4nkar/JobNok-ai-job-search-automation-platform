"""SQLAlchemy engine/session setup.

Two driver paths from one DATABASE_URL:
- async (asyncpg) — used by FastAPI request handlers via get_db()
- sync (psycopg) — used by Celery tasks (no event loop) and Alembic's env.py
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

async_engine = create_async_engine(settings.database_url_async, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


async def get_db():
    """FastAPI dependency yielding a request-scoped AsyncSession.

    Commits on success, rolls back on exception — routes/services never need
    to remember to commit.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Sync path — Celery tasks (no event loop) and Alembic's env.py
sync_engine = create_engine(settings.database_url_sync, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)
