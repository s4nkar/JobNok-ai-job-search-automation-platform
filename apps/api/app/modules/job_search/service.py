"""Recent job search + apply-tracking business logic — SQLAlchemy-backed.

Cross-module note: this module writes to tracker's job_applications table
(via a direct query using JobApplication, not an ORM relationship()) when an
application is marked "applied" — mirrors the pre-migration supabase-py
behavior exactly. See app/modules/job_search/models.py for the FK.
"""

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.cache import check_rate_limit, get_cached, set_cached
from app.shared.utils import row_to_dict
from app.modules.job_search.sources import (
    AdzunaConfigError,
    _tokenize,
    adzuna_country_code,
    canonicalize_job_url,
    dedupe_and_rank,
    fetch_adzuna_raw,
    parse_preferences_prompt,
    score_all,
)
from app.modules.job_search.models import Job, JobSearchApplication
from app.modules.job_search.schemas import (
    JobSearchApplicationCreateRequest,
    JobSearchApplicationUpdateRequest,
    JobSearchRequest,
)
from app.modules.tracker.models import JobApplication


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


async def _check_rate_limit_fail_open(user_id: str) -> None:
    try:
        allowed, _ = await check_rate_limit(user_id, "job_search", settings.rate_limit_job_search_per_day)
    except Exception:
        return
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit of {settings.rate_limit_job_search_per_day} Recent Job Search uses reached. Resets at midnight UTC.",
        )


async def _load_user_job_search_applications(db: AsyncSession, user_id: str) -> list[JobSearchApplication]:
    rows = (
        await db.execute(select(JobSearchApplication).where(JobSearchApplication.user_id == user_id))
    ).scalars().all()
    return list(rows)


async def _load_user_applications_map(db: AsyncSession, user_id: str) -> dict[str, dict]:
    rows = await _load_user_job_search_applications(db, user_id)
    return {r.job_url_canonical: row_to_dict(r) for r in rows if r.job_url_canonical}


def _response_cache_key(payload: dict) -> str:
    parts = [
        str(payload.get("query", "")).strip().lower(),
        str(payload.get("location", "")).strip().lower(),
        str(payload.get("country", "") or "").strip().lower(),
        str(payload.get("posted_within_hours", "")),
        str(payload.get("remote_only", "")),
        str(payload.get("result_limit", "")),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"job_search:adzuna:{digest}"


async def _upsert_jobs_cache(db: AsyncSession, raw_jobs: list[dict], *, origin_tool: str = "recent_job_search") -> None:
    """Upsert every fetched listing into the shared `jobs` cache table, keyed
    by (source, source_job_id) — refreshes last_seen_at/expires_at on repeat
    sightings instead of inserting duplicates."""
    if not raw_jobs:
        return

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.job_search_cache_ttl_days)

    rows = []
    for job in raw_jobs:
        if not job.get("external_job_id"):
            continue
        metadata = job.get("metadata") or {}
        rows.append(
            {
                "source": job["provider_type"],
                "source_job_id": job["external_job_id"],
                "origin_tool": origin_tool,
                "title": job["role"],
                "company": job["company"],
                "location": job["location"],
                "country": metadata.get("country"),
                "description": job.get("description_text") or None,
                "salary_min": metadata.get("salary_min"),
                "salary_max": metadata.get("salary_max"),
                "category": metadata.get("category"),
                "apply_url": job["job_url"],
                "canonical_url": job["job_url_canonical"],
                "posted_at": _parse_dt(job.get("posted_at")),
                "last_seen_at": now,
                "expires_at": expires_at,
            }
        )
    if not rows:
        return

    stmt = pg_insert(Job).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["source", "source_job_id"],
        set_={
            "origin_tool": stmt.excluded.origin_tool,
            "title": stmt.excluded.title,
            "company": stmt.excluded.company,
            "location": stmt.excluded.location,
            "country": stmt.excluded.country,
            "description": stmt.excluded.description,
            "salary_min": stmt.excluded.salary_min,
            "salary_max": stmt.excluded.salary_max,
            "category": stmt.excluded.category,
            "apply_url": stmt.excluded.apply_url,
            "canonical_url": stmt.excluded.canonical_url,
            "posted_at": stmt.excluded.posted_at,
            "last_seen_at": stmt.excluded.last_seen_at,
            "expires_at": stmt.excluded.expires_at,
        },
    )
    await db.execute(stmt)
    await db.flush()


def _job_row_to_raw_dict(row: Job) -> dict:
    """Map a `jobs` table row back into the same normalized dict shape
    `fetch_adzuna_raw` produces, so `score_all`/`_score_job` can run on
    DB-sourced candidates unchanged."""
    return {
        "source_name": "Adzuna" if row.source == "adzuna" else row.source.title(),
        "provider_type": row.source,
        "external_job_id": row.source_job_id,
        "company": row.company,
        "role": row.title,
        "location": row.location,
        "job_url": row.apply_url,
        "job_url_canonical": row.canonical_url,
        "posted_at": row.posted_at.isoformat() if row.posted_at else None,
        "description_text": row.description or "",
        "metadata": {
            "country": row.country,
            "salary_min": float(row.salary_min) if row.salary_min is not None else None,
            "salary_max": float(row.salary_max) if row.salary_max is not None else None,
            "category": row.category,
        },
    }


async def _fetch_db_candidates(db: AsyncSession, payload: dict) -> list[dict]:
    """Coarse pre-filter over the shared `jobs` cache — bounded, not exact
    matching. `score_all`/`_score_job` does the precise per-item decision
    afterward, identically for these DB-sourced candidates and for anything
    freshly fetched from Adzuna, so matching semantics never diverge between
    the two sources.
    """
    country_code = adzuna_country_code(payload.get("country")) or adzuna_country_code(payload.get("location"))
    if not country_code:
        # Can't pass _score_job's country-match gate anyway — skip the DB
        # round-trip and let the caller fall through to fetch_adzuna_raw,
        # which raises the same AdzunaConfigError for an unresolved country.
        return []

    result_limit = int(payload.get("result_limit") or 10)
    candidate_cap = max(300, result_limit * 20)

    conditions = [Job.expires_at > datetime.now(timezone.utc), Job.country == country_code]

    posted_within_hours = payload.get("posted_within_hours")
    if posted_within_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=posted_within_hours)
        conditions.append(Job.posted_at > cutoff)

    query_tokens = _tokenize(str(payload.get("query") or ""))
    if query_tokens:
        conditions.append(
            or_(*[or_(Job.title.ilike(f"%{token}%"), Job.description.ilike(f"%{token}%")) for token in query_tokens])
        )

    rows = (
        await db.execute(
            select(Job).where(*conditions).order_by(Job.posted_at.desc().nulls_last()).limit(candidate_cap)
        )
    ).scalars().all()

    return [_job_row_to_raw_dict(row) for row in rows]


async def search_recent_jobs(db: AsyncSession, user_id: str, body: JobSearchRequest) -> dict:
    await _check_rate_limit_fail_open(user_id)

    user_applications = await _load_user_applications_map(db, user_id)
    payload = body.model_dump()
    preferences = await parse_preferences_prompt(payload.get("preferences_prompt"))
    limit = payload.get("result_limit", 10)

    cache_key = _response_cache_key(payload)
    try:
        cached = await get_cached(cache_key)
    except Exception:
        cached = None
    if cached:
        try:
            raw_jobs = json.loads(cached)
            scored = dedupe_and_rank(score_all(raw_jobs, payload, preferences, user_applications))
            return {"results": scored[:limit], "parsed_preferences": preferences}
        except json.JSONDecodeError:
            pass

    # DB-first: only call Adzuna for whatever the shared cache doesn't already
    # cover (the shortfall), not a fixed split.
    db_raw_jobs = await _fetch_db_candidates(db, payload)
    db_scored = score_all(db_raw_jobs, payload, preferences, user_applications)

    shortfall = limit - len(db_scored)
    fresh_raw_jobs: list[dict] = []
    if shortfall > 0:
        topup_limit = min(50, shortfall * 3)  # headroom — not everything survives scoring
        topup_payload = {**payload, "result_limit": topup_limit}
        try:
            fresh_raw_jobs = await fetch_adzuna_raw(topup_payload)
        except AdzunaConfigError as exc:
            if not db_scored:
                raise HTTPException(status_code=400, detail=str(exc))
            # DB already has something to show — degrade gracefully instead
            # of failing the whole request over the top-up call.
        else:
            await _upsert_jobs_cache(db, fresh_raw_jobs)

    if db_raw_jobs:
        # Refresh last_seen_at/expires_at for whatever was actually scanned
        # as relevant (bounded by _fetch_db_candidates' filters, not the
        # whole table).
        await _upsert_jobs_cache(db, db_raw_jobs)

    combined_raw = db_raw_jobs + fresh_raw_jobs
    try:
        await set_cached(cache_key, json.dumps(combined_raw), settings.job_search_response_cache_ttl_seconds)
    except Exception:
        pass

    fresh_scored = score_all(fresh_raw_jobs, payload, preferences, user_applications) if fresh_raw_jobs else []
    scored = dedupe_and_rank(db_scored + fresh_scored)
    return {
        "results": scored[:limit],
        "parsed_preferences": preferences,
    }


async def list_job_search_applications(db: AsyncSession, user_id: str) -> list[dict]:
    rows = (
        await db.execute(
            select(JobSearchApplication)
            .where(JobSearchApplication.user_id == user_id)
            .order_by(JobSearchApplication.created_at.desc())
        )
    ).scalars().all()
    return [row_to_dict(r) for r in rows]


async def _find_job_id(
    db: AsyncSession, *, source_name: str, external_job_id: str | None, job_url_canonical: str
) -> str | None:
    """Trace a saved result back to its shared `jobs` cache row, when available."""
    source = source_name.strip().lower()
    if external_job_id:
        row = (
            await db.execute(
                select(Job.id).where(Job.source == source, Job.source_job_id == external_job_id)
            )
        ).scalar_one_or_none()
        if row is not None:
            return str(row)

    row = (
        await db.execute(select(Job.id).where(Job.canonical_url == job_url_canonical))
    ).scalar_one_or_none()
    return str(row) if row is not None else None


async def _upsert_tracker_application(
    db: AsyncSession,
    *,
    user_id: str,
    tracker_id: str | None,
    company: str,
    role: str,
    location: str,
    applied_at: str,
) -> str:
    applied_date = date.fromisoformat(applied_at[:10]) if applied_at else _today()
    notes = f"Synced from Recent Job Search for {location}"

    if tracker_id:
        tracker_row = (
            await db.execute(
                select(JobApplication).where(
                    JobApplication.id == tracker_id, JobApplication.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if tracker_row is not None:
            tracker_row.company = company
            tracker_row.role = role
            tracker_row.applied_at = applied_date
            tracker_row.status = "Applied"
            tracker_row.notes = notes
            await db.flush()
            return str(tracker_row.id)

    new_row = JobApplication(
        user_id=user_id, company=company, role=role, applied_at=applied_date,
        status="Applied", notes=notes,
    )
    db.add(new_row)
    await db.flush()
    return str(new_row.id)


async def create_job_search_application(
    db: AsyncSession, user_id: str, body: JobSearchApplicationCreateRequest
) -> dict:
    job_url = str(body.job_url)
    job_url_canonical = canonicalize_job_url(str(body.job_url_canonical or body.job_url))

    existing = (
        await db.execute(
            select(JobSearchApplication).where(
                JobSearchApplication.user_id == user_id,
                JobSearchApplication.job_url_canonical == job_url_canonical,
            )
        )
    ).scalar_one_or_none()

    applied_at_str = body.applied_at
    tracker_id = str(existing.tracker_application_id) if (existing and existing.tracker_application_id) else None
    if body.application_status == "applied":
        tracker_id = await _upsert_tracker_application(
            db,
            user_id=user_id,
            tracker_id=tracker_id,
            company=body.company,
            role=body.role,
            location=body.location,
            applied_at=applied_at_str or datetime.now(timezone.utc).isoformat(),
        )

    if body.application_status == "applied" and not applied_at_str:
        applied_at_str = datetime.now(timezone.utc).isoformat()

    job_id = await _find_job_id(
        db, source_name=body.source_name, external_job_id=body.external_job_id, job_url_canonical=job_url_canonical
    )

    fields = dict(
        job_url=job_url,
        job_url_canonical=job_url_canonical,
        source_name=body.source_name,
        external_job_id=body.external_job_id,
        company=body.company,
        role=body.role,
        location=body.location,
        posted_at=_parse_dt(body.posted_at),
        applied_at=_parse_dt(applied_at_str),
        application_status=body.application_status,
        citation_payload=body.citation_payload,
        search_context=body.search_context,
        user_id=user_id,
        tracker_application_id=tracker_id,
        job_id=job_id,
        discovered_at=existing.discovered_at if existing else datetime.now(timezone.utc),
    )

    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        await db.flush()
        await db.refresh(existing)
        return row_to_dict(existing)

    new_row = JobSearchApplication(**fields)
    db.add(new_row)
    await db.flush()
    await db.refresh(new_row)
    return row_to_dict(new_row)


async def update_job_search_application(
    db: AsyncSession, user_id: str, application_id: str, body: JobSearchApplicationUpdateRequest
) -> dict:
    existing = (
        await db.execute(
            select(JobSearchApplication).where(
                JobSearchApplication.id == application_id, JobSearchApplication.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="Not found")

    applied_at_str = body.applied_at
    if body.application_status == "applied" and not applied_at_str:
        applied_at_str = datetime.now(timezone.utc).isoformat()

    if body.application_status == "applied":
        tracker_id = await _upsert_tracker_application(
            db,
            user_id=user_id,
            tracker_id=str(existing.tracker_application_id) if existing.tracker_application_id else None,
            company=existing.company,
            role=existing.role,
            location=existing.location,
            applied_at=applied_at_str or (existing.applied_at.isoformat() if existing.applied_at else datetime.now(timezone.utc).isoformat()),
        )
        existing.tracker_application_id = tracker_id

    existing.application_status = body.application_status
    # Matches original semantics exactly: applied_at is always overwritten with
    # whatever was resolved above, including None (clears it) when status isn't
    # "applied" and no applied_at was supplied.
    existing.applied_at = _parse_dt(applied_at_str)

    await db.flush()
    await db.refresh(existing)
    return row_to_dict(existing)
