import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, Text, UniqueConstraint, desc, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, UUIDPKMixin, CreatedAtMixin


class Job(Base, UUIDPKMixin, CreatedAtMixin):
    """Shared, deduplicated cache of external job listings (e.g. Adzuna).

    No user_id, this table is fully shared across every user's searches,
    mirroring the `startup_hunt_sources`-style shared-row precedent, just
    with no per-user rows at all (see app/modules/startup_hunt/models.py).
    """

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="jobs_source_job_id_key"),
        Index("jobs_canonical_url_idx", "canonical_url"),
        Index("jobs_expires_at_idx", "expires_at"),
        # Backs query_job_cache_candidates()'s country + posted_at filter/sort below.
        # Added by alembic/versions/e2f7c9a4b8d1_add_jobs_origin_tool_and_search_index.py
        # It must stay declared here too, or a future autogenerate will propose dropping it.
        Index("jobs_country_posted_at_idx", "country", desc("posted_at")),
        # Backs query_job_cache_candidates()'s ILIKE '%token%' title/description filter -
        # a leading-wildcard ILIKE can't use a plain B-tree index, so without a trigram
        # GIN index every DB-first lookup is a full table scan once `jobs` has volume.
        # Added by alembic/versions/a22ae866fa45_add_jobs_trigram_search_indexes.py
        # (also enables the pg_trgm extension) - must stay declared here too, or a
        # future autogenerate will propose dropping it.
        Index("jobs_title_trgm_idx", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
        Index(
            "jobs_description_trgm_idx",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"},
        ),
    )

    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_job_id: Mapped[str] = mapped_column(Text, nullable=False)
    # Which internal tool/feature fetched this row (e.g. "recent_job_search",
    # later "startup_hunt"), distinct from `source`, which is the external
    # provider (e.g. "adzuna"). Lets multiple tools share this cache without
    # losing track of where a row came from.
    origin_tool: Mapped[str] = mapped_column(Text, nullable=False, server_default="recent_job_search")
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
    # Snapshotted from the search result at apply-time. Adzuna's own text, not
    # AI-generated, but capped at ~500 chars by their /search endpoint (no
    # param lifts this) - a preview, not the full posting. Still lets
    # resume-tailor/interview-prep prefill with something real instead of
    # just "{role} at {company}".
    job_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    applied_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    application_status: Mapped[str] = mapped_column(Text, server_default="saved", nullable=False)
    # Cross-module FK to tracker's job_applications, declared as a plain FK
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
    # Trigger-managed (set_updated_at()), no ORM onupdate, see shared/models.py note.
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


async def query_job_cache_candidates(
    db: AsyncSession,
    *,
    country_code: str,
    query_tokens: list[str],
    posted_within_hours: int | None,
    limit: int,
    include_null_country: bool = False,
    allowed_sources: set[str] | None = None,
) -> list[Job]:
    """Coarse, bounded pre-filter over the shared `jobs` cache, not exact
    matching, just narrows the candidate pool. Callers run their own
    fine-grained scorer over the result (e.g. job_search's `_score_job` or
    startup_hunt's `_score_opportunity`), identically to how they score
    freshly-fetched external results, so matching semantics never diverge
    between DB-sourced and live-fetched candidates. Shared across modules
    (job_search and startup_hunt both call this) since it's a query against
    one shared table, each caller maps the returned rows into its own
    dict shape afterward, since those shapes genuinely differ per tool.

    include_null_country: some providers have no country field at all (e.g.
    job_search's Arbeitnow provider), so their cached rows are written with
    country=None and would otherwise never be retrievable by any
    country-scoped search. Opt-in and defaults to the original strict
    behavior, since it's unverified whether every caller's own scorer
    (specifically startup_hunt's) handles a missing country signal as
    gracefully as job_search's does.

    allowed_sources: restricts results to these `Job.source` values (e.g.
    only currently-enabled providers). None = no filter (every cached
    source is eligible), matching the original behavior. Needed because a
    provider's kill switch (e.g. `job_search_adzuna_enabled=False`) only
    gates *live* fetches via `applicable_providers()` - without this, a
    disabled provider's already-cached rows would keep surfacing from the
    DB indefinitely (up to their 14-day TTL), silently defeating the kill
    switch's whole point.
    """
    country_condition = (
        or_(Job.country == country_code, Job.country.is_(None))
        if include_null_country
        else Job.country == country_code
    )
    conditions = [Job.expires_at > datetime.now(timezone.utc), country_condition]

    if allowed_sources is not None:
        conditions.append(Job.source.in_(allowed_sources))

    if posted_within_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=posted_within_hours)
        conditions.append(Job.posted_at > cutoff)

    if query_tokens:
        conditions.append(
            or_(*[or_(Job.title.ilike(f"%{token}%"), Job.description.ilike(f"%{token}%")) for token in query_tokens])
        )

    rows = (
        await db.execute(
            select(Job).where(*conditions).order_by(Job.posted_at.desc().nulls_last()).limit(limit)
        )
    ).scalars().all()

    return list(rows)


async def touch_job_cache_rows(db: AsyncSession, job_ids: list[uuid.UUID], *, ttl_days: int) -> None:
    """Refresh last_seen_at/expires_at for already-cached rows a search actually
    used as candidates, cheaper than re-running the full upsert for rows that
    already exist and haven't changed."""
    if not job_ids:
        return
    now = datetime.now(timezone.utc)
    await db.execute(
        Job.__table__.update()
        .where(Job.id.in_(job_ids))
        .values(last_seen_at=now, expires_at=now + timedelta(days=ttl_days))
    )
    await db.flush()
