import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, Text, func, text
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
    # Best-effort link back to the global crawler registry (see CompanyRegistry
    # below) when this user's saved company matches a canonical crawled record
    # by domain. Nullable and never required - this table keeps its own
    # per-user snapshot regardless (see _upsert_company in service.py).
    registry_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("company_registry.id", ondelete="SET NULL"), nullable=True
    )
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
    # Traces this save back to the shared jobs cache row it came from, when
    # available (mirrors job_search_applications.job_id). Nullable: this table
    # keeps its own denormalized snapshot regardless — audit trail even if the
    # cached listing later expires or the row is only theirstack-sourced.
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
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

    A row starts life via the resolve flow (see resolver.py) - the user
    types a company name or pastes a careers URL, and type/slug/url get
    filled in automatically instead of the user configuring them by hand.
    status tracks where that resolution is: 'resolved' rows are searchable
    immediately (type/slug always set); 'pending' ones are still being
    worked on by the background resolver (type/slug still null, not yet
    included in any search - see build_seeded_sources); 'failed' ones
    surface resolution_error so the UI can offer manual entry as a
    fallback. Rows added via the old manual type/slug/url form (kept as
    that fallback) are created 'resolved' directly, skipping this pipeline
    entirely - they're already exactly what a resolution would produce.
    """

    __tablename__ = "startup_hunt_sources"
    __table_args__ = (
        CheckConstraint(
            "status in ('resolved', 'pending', 'failed')",
            name="startup_hunt_sources_status_check",
        ),
        Index("startup_hunt_sources_user_id_idx", "user_id"),
        Index("startup_hunt_sources_status_idx", "status"),
        # Backs the cross-user "has anyone already resolved this company"
        # reuse lookup in resolver.py (a case-insensitive match on `name`,
        # done in Python via func.lower() in the query - this table stays
        # small (curated companies, not raw listings), so a plain index is
        # enough rather than a dedicated functional index).
        Index("startup_hunt_sources_name_idx", "name"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=True
    )
    # Nullable now - a 'pending' row doesn't know its ATS type yet.
    type: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}", nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default="resolved", nullable=False)
    resolution_error: Mapped[str | None] = mapped_column(Text, nullable=True)


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


class CompanyRegistry(Base, UUIDPKMixin, CreatedAtMixin):
    """Global, deduplicated registry of startups discovered by the background
    crawler pipeline (see discovery/, ingestion/, workers/) - one row per
    real-world company, never per-user. Distinct from StartupHuntSource
    (a user-facing "My Sources" ATS board a person explicitly added) and from
    StartupHuntCompany (a per-user snapshot tied to that user's saved
    opportunities/contacts) - this table is the crawler's own bookkeeping,
    never read directly by any user-facing endpoint.

    Lifecycle: discovered -> resolving -> resolved -> active, with
    no_careers_page/no_jobs/failed/disabled as terminal-ish states a company
    can fall into at the resolution or sync stage. See workers/ for the state
    transitions.
    """

    __tablename__ = "company_registry"
    __table_args__ = (
        CheckConstraint(
            "status in ('discovered', 'resolving', 'resolved', 'active', "
            "'no_careers_page', 'no_jobs', 'failed', 'disabled')",
            name="company_registry_status_check",
        ),
        CheckConstraint(
            "crawl_priority in ('high', 'normal', 'low')",
            name="company_registry_crawl_priority_check",
        ),
        # Partial unique indexes, not table-level UNIQUE constraints - both
        # dedup keys are optional (a row can start life with neither, e.g.
        # domain unknown until resolution), so a plain UNIQUE constraint
        # would reject every second NULL-domain row as a duplicate of the
        # first (NULL <> NULL is the only case Postgres exempts from a table
        # constraint's rejection, but partial indexes make the "when does
        # uniqueness apply" condition explicit instead of relying on that).
        Index(
            "company_registry_domain_key", "domain", unique=True,
            postgresql_where=text("domain IS NOT NULL"),
        ),
        Index(
            "company_registry_discovery_source_id_key", "discovery_source", "discovery_source_id", unique=True,
            postgresql_where=text("discovery_source_id IS NOT NULL"),
        ),
        Index("company_registry_normalized_name_idx", "normalized_name"),
        Index("company_registry_status_idx", "status"),
        Index(
            "company_registry_next_crawl_idx", "next_crawl_at",
            postgresql_where=Text("status = 'active'"),
        ),
        # startup_scout/service.py::_company_registry_candidates filters with
        # ILIKE '%token%' on city/country - a leading-wildcard ILIKE can't use
        # a plain B-tree index, so this must be a GIN trigram index instead
        # (same pattern as jobs.title/description, see job_search/models.py)
        # - must stay declared here too, or a future `alembic revision
        # --autogenerate` would propose dropping an index it doesn't know
        # about (see migration 524f297bbadf).
        Index("company_registry_city_trgm_idx", "city", postgresql_using="gin", postgresql_ops={"city": "gin_trgm_ops"}),
        Index(
            "company_registry_country_trgm_idx", "country",
            postgresql_using="gin", postgresql_ops={"country": "gin_trgm_ops"},
        ),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free text, both discovery paths populate it (StartupMap's own JSON-LD
    # `description` field; startup_scout's scraped-snippet description) - was
    # discarded entirely at write-back time until this column existed, which
    # is why a company_registry (L2 cache)-served search result always showed
    # "No description available" even for companies whose live discovery did
    # find one.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Canonical lowercase-hyphenated form (e.g. "series-a") - see
    # app/shared/funding_stages.py, the single vocabulary both discovery
    # paths (StartupMap's `keywords` field, startup_scout's DDG-snippet
    # parsing) write into. Stored canonical, not display form, since
    # matching a search request's funding_stages filter is the actual DB use
    # case - convert to Title-Case only when building a response.
    funding_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Numeric, not a bucket-string, deliberately: startup_scout's own
    # detected ranges ("51-100", "101-250") use different granularity than
    # the frontend's filter buckets ("51-200", "201-500") - an exact string
    # match between the two would silently never fire. Storing the actual
    # min/max lets filtering do a numeric overlap check against whatever
    # bucket a search requested, regardless of which granularity either
    # discovery path happened to detect at.
    employee_count_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employee_count_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discovery_source: Mapped[str] = mapped_column(Text, nullable=False)
    discovery_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovery_source_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    career_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ats_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    ats_identifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, server_default="discovered", nullable=False)
    crawl_frequency_hours: Mapped[int] = mapped_column(Integer, server_default="48", nullable=False)
    crawl_priority: Mapped[str] = mapped_column(Text, server_default="normal", nullable=False)
    last_discovered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    last_resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    next_crawl_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_job_found_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_job_change_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Trigger-managed (set_updated_at()) — no ORM onupdate, see shared/models.py note.
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
