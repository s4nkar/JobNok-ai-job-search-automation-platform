import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, Text, UniqueConstraint, desc, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, UUIDPKMixin, CreatedAtMixin


class Job(Base, UUIDPKMixin, CreatedAtMixin):
    """Shared, deduplicated cache of external job listings (e.g. Adzuna).

    No user_id — this table is fully shared across every user's searches,
    mirroring the `startup_hunt_sources`-style shared-row precedent, just
    with no per-user rows at all (see app/modules/startup_hunt/models.py).
    """

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="jobs_source_job_id_key"),
        Index("jobs_canonical_url_idx", "canonical_url"),
        Index("jobs_expires_at_idx", "expires_at"),
    )

    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_job_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    apply_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class JobSearchApplication(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "job_search_applications"
    __table_args__ = (
        CheckConstraint(
            "application_status in ('saved', 'applied', 'skipped')",
            name="job_search_applications_status_check",
        ),
        # A unique INDEX, not a table-level UNIQUE constraint.
        Index(
            "job_search_applications_user_job_url_key",
            "user_id",
            "job_url_canonical",
            unique=True,
        ),
        Index("job_search_applications_status_idx", "application_status"),
        Index("job_search_applications_tracker_idx", "tracker_application_id"),
        Index("job_search_applications_posted_idx", desc("posted_at")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    job_url: Mapped[str] = mapped_column(Text, nullable=False)
    job_url_canonical: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    external_job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    applied_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    application_status: Mapped[str] = mapped_column(Text, server_default="saved", nullable=False)
    # Cross-module FK to tracker's job_applications — declared as a plain FK
    # column, no ORM relationship() across module boundaries (see plan notes).
    tracker_application_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("job_applications.id", ondelete="SET NULL"), nullable=True
    )
    # Traces this save back to the shared jobs cache row it came from, when
    # available. Nullable: this table keeps its own denormalized snapshot
    # regardless (audit trail even if the cached listing later expires).
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    citation_payload: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    search_context: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    # Trigger-managed (set_updated_at()) — no ORM onupdate, see shared/models.py note.
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
