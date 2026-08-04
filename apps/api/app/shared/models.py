"""Shared SQLAlchemy declarative base and mixins used by every module's models.py."""

import uuid
from datetime import datetime

from sqlalchemy import Column, Table, text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# Minimal, unmanaged stub of Supabase's auth.users table — exists purely so
# SQLAlchemy can resolve profiles.id's ForeignKey("auth.users.id") when
# sorting/creating tables. Alembic is told to ignore this table entirely
# (see include_object in alembic/env.py) since it's Supabase/GoTrue-managed,
# not something this app's migrations should ever create/alter/drop.
auth_users = Table(
    "users",
    Base.metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    schema="auth",
    info={"is_external": True},
)


class UUIDPKMixin:
    """Server-generated UUID primary key (`default uuid_generate_v4()` in schema.sql)."""

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# NOTE: deliberately no UpdatedAtMixin with an ORM `onupdate=`. Several tables
# (job_applications, job_search_applications, startup_hunt_companies,
# startup_hunt_opportunities, startup_scout_companies) have a Postgres
# `BEFORE UPDATE` trigger (set_updated_at()) that unconditionally overwrites
# updated_at server-side. Declare `updated_at` on those models as a plain
# server-defaulted column with no ORM `onupdate`, and call
# `await session.refresh(obj)` after an UPDATE to pick up the trigger-set value.
