"""Alembic environment — always runs against the sync (psycopg) engine, even
though the FastAPI app itself is async. This is standard practice; there's no
need for an async env.py unless a real need arises.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.shared.models import Base

# Import every module's models.py so its tables register on Base.metadata
# before autogenerate runs — a model module never imported here means its
# table is silently missing from the diff.
from app.modules.profile.models import Profile  # noqa: F401
from app.modules.templates.models import Template  # noqa: F401
from app.modules.bulk_email.models import EmailCampaign, EmailRecipient  # noqa: F401
from app.modules.tracker.models import JobApplication  # noqa: F401
from app.modules.job_search.models import JobSearchApplication  # noqa: F401
from app.modules.startup_hunt.models import (  # noqa: F401
    StartupHuntCompany,
    StartupHuntOpportunity,
    StartupHuntContact,
    OpportunityArtifact,
)
from app.modules.startup_scout.models import StartupScoutCompany, StartupScoutContact  # noqa: F401
from app.modules.linkedin_fill.models import LinkedinCache  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(object, name, type_, reflected, compare_to):
    """Exclude auth.users — it's a Supabase/GoTrue-managed table that only
    exists in our metadata so profiles.id's FK can be resolved (see
    app/shared/models.py). Alembic must never try to create/alter/drop it.
    """
    if type_ == "table" and object.info.get("is_external"):
        return False
    if type_ == "foreign_key_constraint" and getattr(object.column.table, "info", {}).get("is_external"):
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
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
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
