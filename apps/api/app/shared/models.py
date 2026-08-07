"""Shared SQLAlchemy declarative base and mixins used by every module's models.py."""

import uuid
from datetime import datetime

from sqlalchemy import text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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
