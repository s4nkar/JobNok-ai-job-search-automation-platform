"""Startup Hunt business logic — SQLAlchemy-backed.

Cross-module note: writes to tracker's job_applications table (via a direct
query using JobApplication, not an ORM relationship()) when an opportunity is
marked "applied" — mirrors the pre-migration supabase-py behavior exactly.
"""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.repository import UserScopedRepository
from app.shared.utils import row_to_dict
from app.modules.startup_hunt.engine import canonicalize_url, extract_domain, search_startup_hunt
from app.modules.startup_hunt.models import (
    OpportunityArtifact,
    StartupHuntCompany,
    StartupHuntContact,
    StartupHuntOpportunity,
)
from app.modules.startup_hunt.schemas import (
    StartupHuntOpportunityCreateRequest,
    StartupHuntOpportunityUpdateRequest,
)
from app.modules.tracker.models import JobApplication


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class OpportunityRepository(UserScopedRepository[StartupHuntOpportunity]):
    model = StartupHuntOpportunity


async def _load_opportunities(db: AsyncSession, user_id: str) -> list[StartupHuntOpportunity]:
    rows = (
        await db.execute(select(StartupHuntOpportunity).where(StartupHuntOpportunity.user_id == user_id))
    ).scalars().all()
    return list(rows)


async def _load_opportunity_map(db: AsyncSession, user_id: str) -> dict[str, dict]:
    opportunities = await _load_opportunities(db, user_id)
    output: dict[str, dict] = {}
    for row in opportunities:
        d = row_to_dict(row)
        key = d.get("canonical_job_url") or (
            f'{(d.get("company_name") or "").strip().lower()}|'
            f'{(d.get("role_title") or "").strip().lower()}|'
            f'{(d.get("location") or "").strip().lower()}'
        )
        output[key] = d
    return output


async def search_startup_hunt_opportunities(db: AsyncSession, user_id: str, body) -> dict:
    existing = await _load_opportunity_map(db, user_id)
    (
        results, overflow_results, filtered_out, parsed_strategy,
        configured_source_count, source_result_counts, source_diagnostics,
    ) = await search_startup_hunt(body.model_dump(), existing)
    return {
        "results": results,
        "overflow_results": overflow_results,
        "filtered_out": filtered_out,
        "parsed_strategy": parsed_strategy,
        "configured_source_count": configured_source_count,
        "source_result_counts": source_result_counts,
        "source_diagnostics": source_diagnostics,
    }


async def list_startup_hunt_opportunities(db: AsyncSession, user_id: str) -> list[dict]:
    rows = await OpportunityRepository(db).list(user_id, order_by=StartupHuntOpportunity.created_at.desc())
    return [row_to_dict(r) for r in rows]


async def get_startup_hunt_opportunity(db: AsyncSession, user_id: str, opportunity_id: str) -> dict:
    row = await OpportunityRepository(db).get(user_id, opportunity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="startup_hunt_opportunities row not found")
    return row_to_dict(row)


async def list_startup_hunt_contacts(db: AsyncSession, user_id: str, opportunity_id: str | None) -> list[dict]:
    stmt = select(StartupHuntContact).where(StartupHuntContact.user_id == user_id)
    if opportunity_id:
        stmt = stmt.where(StartupHuntContact.opportunity_id == opportunity_id)
    stmt = stmt.order_by(StartupHuntContact.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [row_to_dict(r) for r in rows]


async def get_artifact_counts(db: AsyncSession, user_id: str) -> dict[str, int]:
    rows = (
        await db.execute(
            select(OpportunityArtifact.opportunity_id, func.count())
            .where(OpportunityArtifact.user_id == user_id, OpportunityArtifact.opportunity_id.is_not(None))
            .group_by(OpportunityArtifact.opportunity_id)
        )
    ).all()
    return {str(oid): count for oid, count in rows}


async def list_opportunity_artifacts(db: AsyncSession, user_id: str, opportunity_id: str) -> list[dict]:
    rows = (
        await db.execute(
            select(OpportunityArtifact)
            .where(OpportunityArtifact.user_id == user_id, OpportunityArtifact.opportunity_id == opportunity_id)
            .order_by(OpportunityArtifact.created_at.desc())
        )
    ).scalars().all()
    return [row_to_dict(r) for r in rows]


async def create_opportunity_artifact(db: AsyncSession, user_id: str, opportunity_id: str, body: dict) -> dict:
    artifact_type = body.get("artifact_type", "")
    if artifact_type not in {"resume_analysis", "cover_letter", "interview_prep"}:
        raise HTTPException(status_code=422, detail="Invalid artifact_type")
    obj = OpportunityArtifact(
        user_id=user_id,
        opportunity_id=opportunity_id,
        artifact_type=artifact_type,
        tool_used=body.get("tool_used", artifact_type),
        content=body.get("content", ""),
        metadata_=body.get("metadata", {}),
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return row_to_dict(obj)


async def delete_opportunity_artifact(db: AsyncSession, user_id: str, opportunity_id: str, artifact_id: str) -> None:
    row = (
        await db.execute(
            select(OpportunityArtifact).where(
                OpportunityArtifact.id == artifact_id,
                OpportunityArtifact.opportunity_id == opportunity_id,
                OpportunityArtifact.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await db.delete(row)
    await db.flush()


async def _upsert_tracker_application(
    db: AsyncSession, *, user_id: str, tracker_id: str | None, company: str, role: str, location: str
) -> str:
    applied_date = datetime.now(timezone.utc).date()
    notes = f"Synced from Startup Hunt for {location}"

    if tracker_id:
        tracker_row = (
            await db.execute(
                select(JobApplication).where(JobApplication.id == tracker_id, JobApplication.user_id == user_id)
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
        user_id=user_id, company=company, role=role, applied_at=applied_date, status="Applied", notes=notes
    )
    db.add(new_row)
    await db.flush()
    return str(new_row.id)


async def _upsert_company(db: AsyncSession, user_id: str, payload: dict) -> str:
    company_payload = payload.get("company_payload") or {}
    existing = (
        await db.execute(
            select(StartupHuntCompany).where(
                StartupHuntCompany.user_id == user_id, StartupHuntCompany.company_name == payload["company_name"]
            )
        )
    ).scalar_one_or_none()

    fields = dict(
        company_name=payload["company_name"],
        company_domain=payload.get("company_domain"),
        company_website_url=payload.get("company_website_url"),
        company_careers_url=payload.get("company_careers_url"),
        country=payload.get("country"),
        city=company_payload.get("city"),
        stage=company_payload.get("stage"),
        company_size=company_payload.get("company_size"),
        ai_relevance=company_payload.get("ai_relevance"),
        english_friendly=bool(company_payload.get("english_friendly")),
        relocation_support=company_payload.get("relocation_support"),
        source_payload=company_payload,
    )

    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        await db.flush()
        return str(existing.id)

    new_row = StartupHuntCompany(user_id=user_id, **fields)
    db.add(new_row)
    await db.flush()
    return str(new_row.id)


async def _replace_contacts(
    db: AsyncSession, user_id: str, opportunity_id: str, contacts: list[dict], company_id: str | None
) -> None:
    await db.execute(
        StartupHuntContact.__table__.delete().where(
            StartupHuntContact.user_id == user_id, StartupHuntContact.opportunity_id == opportunity_id
        )
    )
    if not contacts:
        await db.flush()
        return
    for contact in contacts:
        db.add(
            StartupHuntContact(
                user_id=user_id,
                opportunity_id=opportunity_id,
                company_id=company_id,
                name=contact.get("name"),
                title=contact.get("title"),
                contact_type=contact.get("contact_type"),
                email=contact.get("email"),
                email_confidence=contact.get("email_confidence"),
                linkedin_url=contact.get("linkedin_url"),
                source=contact.get("source"),
                provider_chain=contact.get("provider_chain") or [],
            )
        )
    await db.flush()


def _url_fields(payload: dict) -> dict:
    direct_apply_url = str(payload["direct_apply_url"]) if payload.get("direct_apply_url") else None
    canonical_job_url = (
        str(payload["canonical_job_url"])
        if payload.get("canonical_job_url")
        else (canonicalize_url(direct_apply_url) if direct_apply_url else None)
    )
    portal_job_url = str(payload["portal_job_url"]) if payload.get("portal_job_url") else None
    company_website_url = str(payload["company_website_url"]) if payload.get("company_website_url") else None
    company_careers_url = str(payload["company_careers_url"]) if payload.get("company_careers_url") else None
    return {
        "direct_apply_url": direct_apply_url,
        "canonical_job_url": canonical_job_url,
        "portal_job_url": portal_job_url,
        "company_website_url": company_website_url,
        "company_careers_url": company_careers_url,
    }


async def create_startup_hunt_opportunity(
    db: AsyncSession, user_id: str, body: StartupHuntOpportunityCreateRequest
) -> dict:
    payload = body.model_dump()
    payload.update(_url_fields(payload))
    payload["company_domain"] = payload.get("company_domain") or extract_domain(
        payload["company_website_url"] or payload["company_careers_url"] or payload["direct_apply_url"]
    )
    payload["discovered_at"] = payload.get("discovered_at") or datetime.now(timezone.utc).isoformat()

    existing = (
        await db.execute(
            select(StartupHuntOpportunity).where(
                StartupHuntOpportunity.user_id == user_id,
                StartupHuntOpportunity.company_name == payload["company_name"],
                StartupHuntOpportunity.role_title == payload["role_title"],
                StartupHuntOpportunity.location == payload["location"],
            )
        )
    ).scalar_one_or_none()

    tracker_id = str(existing.tracker_application_id) if (existing and existing.tracker_application_id) else None
    if payload["opportunity_status"] == "applied":
        tracker_id = await _upsert_tracker_application(
            db, user_id=user_id, tracker_id=tracker_id,
            company=payload["company_name"], role=payload["role_title"], location=payload["location"],
        )

    company_id = await _upsert_company(db, user_id, payload)

    fields = dict(
        company_name=payload["company_name"],
        company_domain=payload["company_domain"],
        company_website_url=payload["company_website_url"],
        company_careers_url=payload["company_careers_url"],
        role_title=payload["role_title"],
        location=payload["location"],
        country=payload.get("country"),
        source_name=payload["source_name"],
        source_type=payload["source_type"],
        direct_apply_url=payload["direct_apply_url"],
        canonical_job_url=payload["canonical_job_url"],
        portal_job_url=payload["portal_job_url"],
        posted_at=_parse_dt(payload.get("posted_at")),
        discovered_at=_parse_dt(payload["discovered_at"]),
        opportunity_kind=payload["opportunity_kind"],
        opportunity_status=payload["opportunity_status"],
        score_total=Decimal(str(payload.get("score_total") or 0)),
        score_labels=payload.get("score_labels") or [],
        score_reasons=payload.get("score_reasons") or [],
        citation_payload=payload["citation_payload"],
        company_payload=payload.get("company_payload") or {},
        search_context=payload.get("search_context") or {},
        user_id=user_id,
        tracker_application_id=tracker_id,
        company_id=company_id,
    )

    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        await db.flush()
        await db.refresh(existing)
        await _replace_contacts(db, user_id, str(existing.id), payload.get("contacts", []), company_id)
        return row_to_dict(existing)

    new_row = StartupHuntOpportunity(**fields)
    db.add(new_row)
    await db.flush()
    await db.refresh(new_row)
    await _replace_contacts(db, user_id, str(new_row.id), payload.get("contacts", []), company_id)
    return row_to_dict(new_row)


async def update_startup_hunt_opportunity(
    db: AsyncSession, user_id: str, opportunity_id: str, body: StartupHuntOpportunityUpdateRequest
) -> dict:
    existing = (
        await db.execute(
            select(StartupHuntOpportunity).where(
                StartupHuntOpportunity.id == opportunity_id, StartupHuntOpportunity.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="Not found")

    direct_apply_url = str(body.direct_apply_url) if body.direct_apply_url else existing.direct_apply_url
    canonical_job_url = str(body.canonical_job_url) if body.canonical_job_url else existing.canonical_job_url

    if body.opportunity_status == "applied":
        tracker_id = await _upsert_tracker_application(
            db, user_id=user_id,
            tracker_id=str(existing.tracker_application_id) if existing.tracker_application_id else None,
            company=existing.company_name, role=existing.role_title, location=existing.location,
        )
        existing.tracker_application_id = tracker_id

    existing.opportunity_status = body.opportunity_status
    existing.direct_apply_url = direct_apply_url
    existing.canonical_job_url = canonical_job_url

    await db.flush()
    await db.refresh(existing)
    return row_to_dict(existing)


async def delete_startup_hunt_opportunity(db: AsyncSession, user_id: str, opportunity_id: str) -> None:
    ok = await OpportunityRepository(db).delete(user_id, opportunity_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
