import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, UUIDPKMixin, CreatedAtMixin


class StartupScoutCompany(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "startup_scout_companies"
    __table_args__ = (
        CheckConstraint(
            "crawl_status in ('pending', 'crawling', 'enriched', 'partial', 'failed')",
            name="startup_scout_crawl_status_check",
        ),
        Index("startup_scout_companies_user_idx", "user_id"),
        Index("startup_scout_companies_status_idx", "crawl_status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_they_do: Mapped[str | None] = mapped_column(Text, nullable=True)
    funding_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_range: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, server_default="web_scrape", nullable=False)
    crawl_status: Mapped[str] = mapped_column(Text, server_default="pending", nullable=False)
    # Trigger-managed (set_updated_at()) — no ORM onupdate, see shared/models.py note.
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class StartupScoutContact(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "startup_scout_contacts"
    __table_args__ = (
        Index("startup_scout_contacts_user_idx", "user_id"),
        Index("startup_scout_contacts_company_idx", "company_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("startup_scout_companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    # Contact-verification fields (Apollo/web-crawl enrichment stage 2) — added
    # to the live schema after the table was first created.
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    verification_url: Mapped[str | None] = mapped_column(Text, nullable=True)
