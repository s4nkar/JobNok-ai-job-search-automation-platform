"""SQLAlchemy engine/session setup.

Async (asyncpg), from DATABASE_URL — used by FastAPI request handlers via
get_db() and by ARQ worker tasks (both run on an event loop).

Alembic (alembic/env.py) uses its own sync engine built from
MIGRATIONS_DATABASE_URL (the direct/unpooled connection), not this module.
"""

from urllib.parse import parse_qs, urlparse

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings


def _asyncpg_url_and_connect_args(url: str) -> tuple[str, dict]:
    """Neon's connection string is libpq-style (?sslmode=require&channel_binding=require),
    but asyncpg's connect() takes those as unrecognized keyword arguments and
    raises `TypeError: connect() got an unexpected keyword argument 'sslmode'`
    - SQLAlchemy's asyncpg dialect passes every query-string key straight
    through as a kwarg, it doesn't translate libpq params itself. Strips the
    query string entirely and translates sslmode into asyncpg's own `ssl=`
    connect_arg instead (asyncpg accepts the same sslmode-style string
    values directly); channel_binding has no asyncpg equivalent and is just
    dropped - TLS still negotiates correctly without it.

    A no-op for a plain URL with no query string (e.g. local dev Postgres),
    so this is safe for every DATABASE_URL shape this app is configured
    with, not just Neon's.
    """
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    connect_args: dict = {}
    sslmode = query.get("sslmode", [None])[0]
    if sslmode:
        connect_args["ssl"] = sslmode
    clean_url = parsed._replace(query="").geturl()
    return clean_url, connect_args


_clean_database_url, _ssl_connect_args = _asyncpg_url_and_connect_args(settings.database_url_async)

async_engine = create_async_engine(
    _clean_database_url,
    pool_pre_ping=True,
    connect_args={
        **_ssl_connect_args,
        # DATABASE_URL is a transaction-mode pooler (Supabase pgbouncer / Neon
        # -pooler endpoint). asyncpg's default client-side prepared-statement
        # caching can collide across pooled connections (DuplicatePreparedStatementError);
        # disabling it makes every query one-shot/unnamed, which is safe under
        # transaction pooling at a small perf cost.
        "statement_cache_size": 0,
    },
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
