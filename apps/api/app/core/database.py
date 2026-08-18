"""SQLAlchemy engine/session setup.

Async (asyncpg), from DATABASE_URL — used by FastAPI request handlers via
get_db() and by ARQ worker tasks (both run on an event loop).

Alembic (alembic/env.py) uses its own sync engine built from
MIGRATIONS_DATABASE_URL (the direct/unpooled connection), not this module.
"""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings

async_engine = create_async_engine(
    settings.database_url_async,
    pool_pre_ping=True,
    # DATABASE_URL is a transaction-mode pooler (Supabase pgbouncer / Neon
    # -pooler endpoint). asyncpg's default client-side prepared-statement
    # caching can collide across pooled connections (DuplicatePreparedStatementError);
    # disabling it makes every query one-shot/unnamed, which is safe under
    # transaction pooling at a small perf cost.
    connect_args={"statement_cache_size": 0},
)
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
