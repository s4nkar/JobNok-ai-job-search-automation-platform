"""Alembic environment — always runs against the sync (psycopg) engine, even
though the FastAPI app itself is async. This is standard practice; there's no
need for an async env.py unless a real need arises.

Uses MIGRATIONS_DATABASE_URL (session-pooler/direct, port 5432), not the
transaction-pooler DATABASE_URL the app runs on — DDL is unreliable through
transaction-mode pooling (see app/core/config.py).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.shared.models import Base
from app.shared import model_registry  # noqa: F401 — registers every table on Base.metadata

config = context.config
config.set_main_option("sqlalchemy.url", settings.migrations_database_url_sync)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
