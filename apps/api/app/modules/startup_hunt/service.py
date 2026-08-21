"""Startup Hunt business logic, SQLAlchemy-backed.

This module intentionally does not write into tracker's job_applications
table - startup_hunt_opportunities is its own tracked list, surfaced in the
Tracker's dedicated "Startup Leads" tab, so a lead marked "applied" here shows
up exactly once instead of also duplicating into the Tracker's manual
Applications tab.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.shared.repository import UserScopedRepository
from app.shared.utils import row_to_dict
from app.modules.job_search.models import Job, query_job_cache_candidates, touch_job_cache_rows
from app.modules.job_search.service import _upsert_jobs_cache
from app.modules.job_search.providers.adzuna import adzuna_country_code
from app.modules.startup_hunt.engine import (
    _dedupe_opportunities,
    _score_opportunity,
    build_seeded_sources,
    canonicalize_url,
    extract_domain,
    parse_strategy_prompt,
    search_startup_hunt,
    tokenize,
)
from app.modules.startup_hunt.models import (
    OpportunityArtifact,
    StartupHuntCompany,
    StartupHuntContact,
    StartupHuntOpportunity,
    StartupHuntSource,
)
from app.modules.startup_hunt.schemas import (
    StartupHuntOpportunityCreateRequest,
    StartupHuntOpportunityUpdateRequest,
    StartupHuntSourceIn,
)


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


def _job_row_to_opportunity_dict(row: Job) -> dict[str, Any]:
    """Map a shared `jobs` cache row into Startup Hunt's opportunity dict shape
    so the existing `_score_opportunity` can run on it unchanged.

    No company_payload/contacts enrichment survives a cache round-trip — the
    generic `jobs` table has no columns for funding stage, company size,
    English-friendly, etc. `_score_opportunity` already treats a missing
    `company_payload` gracefully: it scores neutrally when no stage/size
    filter is set, and hard-excludes the row the moment a user sets an
    explicit `company_stage` filter (since `"x" not in ""` is always True) —
    see the plan notes for why this needed no changes to that function.
    """
    raw_text = f"{row.title} {row.company} {row.description or ''}".strip()
    return {
        # Surfaced through _score_opportunity's return dict unchanged, so the
        # frontend can badge this distinctly from a live theirstack fetch —
        # it fills the theirstack bucket/cap for accounting purposes, but may
        # have actually originated from any provider (see source_name below).
        "cache_hit": True,
        "opportunity_kind": "job",
        "company_name": row.company,
        "company_domain": None,
        "company_website_url": None,
        "company_careers_url": None,
        "role_title": row.title,
        "location": row.location,
        "country": row.country,
        "source_name": "TheirStack" if row.source == "theirstack" else row.source.title(),
        "source_type": "theirstack_search",
        "direct_apply_url": row.apply_url,
        "canonical_job_url": row.canonical_url,
        "portal_job_url": row.apply_url,
        "posted_at": row.posted_at,
        "company_payload": {},
        "contacts": [],
        "raw_text": raw_text,
        "citation": {
            "source_name": "TheirStack",
            "canonical_url": row.canonical_url,
            "job_url": row.apply_url,
            "posted_at": row.posted_at.isoformat() if row.posted_at else None,
            "evidence": ["Matched cached listing"],
            "extraction_note": "Served from the shared job cache.",
        },
    }


def _theirstack_opportunity_to_job_cache_row(item: dict[str, Any]) -> dict[str, Any] | None:
    """Adapt a freshly-fetched theirstack opportunity dict into job_search's
    flat upsert shape, so the existing `_upsert_jobs_cache` can write it into
    the shared `jobs` table unchanged. TheirStack results carry no stable
    per-item ID (confirmed in engine.py's `_normalize_theirstack_items`), so
    the canonical URL doubles as the dedup key — same role canonical URLs
    already play everywhere else in this codebase."""
    canonical_url = item.get("canonical_job_url")
    apply_url = item.get("direct_apply_url") or item.get("portal_job_url") or canonical_url
    if not canonical_url or not apply_url:
        return None
    posted_at = item.get("posted_at")
    country_code = adzuna_country_code(item.get("country")) or None
    return {
        "provider_type": "theirstack",
        "external_job_id": canonical_url,
        "role": item.get("role_title") or "",
        "company": item.get("company_name") or "",
        "location": item.get("location") or "",
        "job_url": apply_url,
        "job_url_canonical": canonical_url,
        "posted_at": posted_at.isoformat() if isinstance(posted_at, datetime) else posted_at,
        "description_text": (item.get("raw_text") or "")[:2000],
        "metadata": {"country": country_code, "salary_min": None, "salary_max": None, "category": None},
    }


async def _fetch_theirstack_db_candidates(
    db: AsyncSession, payload: dict[str, Any], strategy: dict[str, Any], existing: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[uuid.UUID]]:
    """DB-first pre-check for the theirstack bucket only (see plan). Returns
    already-scored opportunity dicts plus the underlying row ids (for TTL
    refresh), or ([], []) if the country can't be resolved, in which case
    the live theirstack fetch's own ProviderError-equivalent handling
    (settings.theirstack_api_key check) takes over exactly as before."""
    country_code = adzuna_country_code(payload.get("country")) or adzuna_country_code(payload.get("location"))
    if not country_code:
        return [], []

    theirstack_limit = int(payload.get("theirstack_limit") or payload.get("result_limit") or 15)
    rows = await query_job_cache_candidates(
        db,
        country_code=country_code,
        query_tokens=tokenize(str(payload.get("query") or "")),
        posted_within_hours=payload.get("posted_within_hours"),
        limit=max(300, theirstack_limit * 20),
    )

    scored: list[dict[str, Any]] = []
    for row in rows:
        item = _job_row_to_opportunity_dict(row)
        scored_item, _ = _score_opportunity(item, payload, strategy, existing)
        if scored_item is not None:
            scored.append(scored_item)

    return scored, [row.id for row in rows]


async def search_startup_hunt_opportunities(db: AsyncSession, user_id: str, body) -> dict:
    existing = await _load_opportunity_map(db, user_id)
    # Global curated sources stay gated behind include_seeded_sources + the
    # "crawler" bucket toggle (unchanged). A user's own sources are always
    # searched when present — there's no reason to hide something they
    # explicitly added behind an unrelated flag.
    global_sources = build_seeded_sources(await list_global_startup_hunt_sources(db))
    user_sources = build_seeded_sources(await list_user_startup_hunt_sources(db, user_id))

    payload = body.model_dump()
    strategy = await parse_strategy_prompt(payload.get("strategy_prompt"))

    # DB-first shortfall check — theirstack bucket only (see plan). The other
    # 6 buckets run exactly as they always have, fully live, every search.
    db_scored: list[dict[str, Any]] = []
    db_job_ids: list[uuid.UUID] = []
    adjusted_payload = payload
    if payload.get("theirstack_enabled", True):
        db_scored, db_job_ids = await _fetch_theirstack_db_candidates(db, payload, strategy, existing)
        theirstack_limit = int(payload.get("theirstack_limit") or payload.get("result_limit") or 15)
        shortfall = theirstack_limit - len(db_scored)
        adjusted_payload = dict(payload)
        if shortfall <= 0:
            adjusted_payload["theirstack_enabled"] = False
        else:
            adjusted_payload["theirstack_limit"] = min(settings.theirstack_max_page_size, shortfall * 2)

    (
        results, overflow_results, filtered_out, parsed_strategy,
        configured_source_count, source_result_counts, source_diagnostics,
    ) = await search_startup_hunt(adjusted_payload, existing, global_sources, user_sources, strategy=strategy)

    # Upsert freshly-fetched theirstack results into the shared cache, and
    # refresh TTL for whatever DB candidates were actually scanned as
    # relevant (bounded by _fetch_theirstack_db_candidates' filters, not the
    # whole table) — same pattern job_search's search_recent_jobs uses.
    fresh_theirstack_rows = [
        row for item in results if item.get("source_type") == "theirstack_search"
        if (row := _theirstack_opportunity_to_job_cache_row(item)) is not None
    ]
    if fresh_theirstack_rows:
        await _upsert_jobs_cache(db, fresh_theirstack_rows, origin_tool="startup_hunt")
    if db_job_ids:
        await touch_job_cache_rows(db, db_job_ids, ttl_days=settings.job_search_cache_ttl_days)

    if db_scored:
        result_limit = int(payload.get("result_limit") or 25)
        combined = _dedupe_opportunities(db_scored + results)
        combined.sort(key=lambda item: -float(item.get("score_total") or 0))
        results = combined[:result_limit]
        overflow_results = combined[result_limit:] + overflow_results

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


async def _find_job_id(db: AsyncSession, *, source_type: str, canonical_job_url: str | None) -> str | None:
    """Trace a saved opportunity back to its shared `jobs` cache row, when
    available. Only theirstack-sourced saves can have one today — the other
    6 buckets don't write into the shared cache yet (see plan)."""
    if source_type != "theirstack_search" or not canonical_job_url:
        return None
    row = (
        await db.execute(
            select(Job.id).where(Job.source == "theirstack", Job.canonical_url == canonical_job_url)
        )
    ).scalar_one_or_none()
    return str(row) if row is not None else None


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

    # Preserves whatever tracker_application_id an already-migrated row happened
    # to carry, but never sets one on new writes - startup_hunt_opportunities is
    # its own tracked list now (the Tracker's "Startup Leads" tab), not synced
    # into the Tracker's manual job_applications table.
    tracker_id = str(existing.tracker_application_id) if (existing and existing.tracker_application_id) else None

    company_id = await _upsert_company(db, user_id, payload)
    job_id = await _find_job_id(
        db, source_type=payload["source_type"], canonical_job_url=payload.get("canonical_job_url")
    )

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
        job_id=job_id,
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


# ── Startup Hunt Sources (global curated + per-user custom) ──────────────

class StartupHuntSourceRepository(UserScopedRepository[StartupHuntSource]):
    model = StartupHuntSource


async def list_global_startup_hunt_sources(db: AsyncSession) -> list[dict]:
    """The curated source list visible to every user (user_id IS NULL) — still
    gated behind include_seeded_sources + the "crawler" bucket toggle."""
    stmt = select(StartupHuntSource).where(StartupHuntSource.user_id.is_(None))
    rows = (await db.execute(stmt)).scalars().all()
    return [row_to_dict(r) for r in rows]


async def list_user_startup_hunt_sources(db: AsyncSession, user_id: str) -> list[dict]:
    """This user's own sources only — for the source-management UI."""
    rows = await StartupHuntSourceRepository(db).list(user_id, order_by=StartupHuntSource.created_at.desc())
    return [row_to_dict(r) for r in rows]


async def create_startup_hunt_source(db: AsyncSession, user_id: str, body: StartupHuntSourceIn) -> dict:
    obj = await StartupHuntSourceRepository(db).create(
        user_id,
        type=body.type,
        name=body.name,
        company=body.company or body.name,
        slug=body.slug,
        url=str(body.url) if body.url else None,
        metadata_=body.metadata,
    )
    return row_to_dict(obj)


async def delete_startup_hunt_source(db: AsyncSession, user_id: str, source_id: str) -> None:
    ok = await StartupHuntSourceRepository(db).delete(user_id, source_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
