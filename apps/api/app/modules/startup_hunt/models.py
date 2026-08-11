import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, CheckConstraint, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, UUIDPKMixin, CreatedAtMixin


class StartupHuntCompany(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "startup_hunt_companies"
    __table_args__ = (
        Index("startup_hunt_companies_user_idx", "user_id"),
        Index("startup_hunt_companies_name_idx", "company_name"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    company_domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_careers_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_size: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_relevance: Mapped[str | None] = mapped_column(Text, nullable=True)
    english_friendly: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    relocation_support: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_payload: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    # Trigger-managed (set_updated_at()) — no ORM onupdate, see shared/models.py note.
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class StartupHuntOpportunity(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "startup_hunt_opportunities"
    __table_args__ = (
        CheckConstraint(
            "opportunity_kind in ('job', 'outreach_lead')",
            name="startup_hunt_opportunity_kind_check",
        ),
        CheckConstraint(
            "opportunity_status in ('saved', 'applied', 'contacted', 'skipped')",
            name="startup_hunt_opportunity_status_check",
        ),
        Index("startup_hunt_opportunities_user_idx", "user_id"),
        Index("startup_hunt_opportunities_status_idx", "opportunity_status"),
        Index("startup_hunt_opportunities_company_idx", "company_name"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("startup_hunt_companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Cross-module FK to tracker's job_applications — plain FK column only.
    tracker_application_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("job_applications.id", ondelete="SET NULL"), nullable=True
    )
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    company_domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_careers_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_title: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    direct_apply_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_job_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    portal_job_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    opportunity_kind: Mapped[str] = mapped_column(Text, server_default="job", nullable=False)
    opportunity_status: Mapped[str] = mapped_column(Text, server_default="saved", nullable=False)
    score_total: Mapped[float] = mapped_column(Numeric, server_default="0", nullable=False)
    score_labels: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}", nullable=False)
    score_reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}", nullable=False)
    citation_payload: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    company_payload: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    search_context: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    # Trigger-managed (set_updated_at()) — no ORM onupdate, see shared/models.py note.
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class StartupHuntContact(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "startup_hunt_contacts"
    __table_args__ = (
        Index("startup_hunt_contacts_user_idx", "user_id"),
        Index("startup_hunt_contacts_opportunity_idx", "opportunity_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("startup_hunt_companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("startup_hunt_opportunities.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_confidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_chain: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}", nullable=False)


class StartupHuntSource(Base, UUIDPKMixin, CreatedAtMixin):
    """A source config fed into search_startup_hunt's seeded-source list.

    user_id NULL = globally curated, visible to every user (replaces the old
    STARTUP_HUNT_SOURCES_JSON env var). user_id set = one user's own private
    addition, only ever merged into that user's own searches.
    """

    __tablename__ = "startup_hunt_sources"
    __table_args__ = (
        Index("startup_hunt_sources_user_id_idx", "user_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=True
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}", nullable=False)


class OpportunityArtifact(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "opportunity_artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_type in ('resume_analysis', 'cover_letter', 'interview_prep')",
            name="opportunity_artifact_type_check",
        ),
        Index("opportunity_artifacts_user_idx", "user_id"),
        Index("opportunity_artifacts_opportunity_idx", "opportunity_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("startup_hunt_opportunities.id", ondelete="CASCADE"),
        nullable=True,
    )
    artifact_type: Mapped[str] = mapped_column(Text, nullable=False)
    tool_used: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default="{}", nullable=False
    )
