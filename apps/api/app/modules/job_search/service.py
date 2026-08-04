"""Recent job search + apply-tracking business logic — SQLAlchemy-backed.

Cross-module note: this module writes to tracker's job_applications table
(via a direct query using JobApplication, not an ORM relationship()) when an
application is marked "applied" — mirrors the pre-migration supabase-py
behavior exactly. See app/modules/job_search/models.py for the FK.
"""

from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.cache import check_rate_limit
from app.shared.utils import row_to_dict
from app.modules.job_search.sources import canonicalize_job_url, load_job_search_sources, search_jobs
from app.modules.job_search.models import JobSearchApplication
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


async def search_recent_jobs(db: AsyncSession, user_id: str, body: JobSearchRequest) -> dict:
    await _check_rate_limit_fail_open(user_id)

    user_applications = await _load_user_applications_map(db, user_id)
    configured_sources = load_job_search_sources()
    results, parsed_preferences = await search_jobs(body.model_dump(), user_applications)
    return {
        "results": results,
        "parsed_preferences": parsed_preferences,
        "configured_source_count": len(configured_sources),
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
