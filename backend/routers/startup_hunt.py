"""Startup Hunt v2 endpoints for startup-first opportunity discovery."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from lib.config import settings
from lib.startup_hunt import canonicalize_url, extract_domain, search_startup_hunt
from lib.redis_client import check_rate_limit
from lib.supabase_client import get_supabase, get_user_id, verify_jwt
from models.schemas import (
    StartupHuntOpportunityCreateRequest,
    StartupHuntOpportunityUpdateRequest,
    StartupHuntSearchRequest,
)

router = APIRouter()


async def _ensure_profile_exists(sb, user_id: str, request: Request) -> None:
    """Upsert a profiles row so FK constraints don't fail for users whose profile trigger missed."""
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    claims = verify_jwt(token)
    email = claims.get("email") or f"{user_id}@unknown.local"
    try:
        await asyncio.to_thread(
            lambda: sb.table("profiles")
            .upsert({"id": user_id, "email": email}, on_conflict="id")
            .execute()
        )
    except Exception:
        pass


async def _check_rate_limit_fail_open(user_id: str) -> None:
    try:
        allowed, _ = await check_rate_limit(user_id, "startup_hunt", settings.rate_limit_startup_hunt_per_day)
    except Exception:
        return
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit of {settings.rate_limit_startup_hunt_per_day} Startup Hunt uses reached. Resets at midnight UTC.",
        )


async def _load_opportunities(user_id: str) -> list[dict]:
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("startup_hunt_opportunities")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return res.data or []


async def _load_opportunity_map(user_id: str) -> dict[str, dict]:
    opportunities = await _load_opportunities(user_id)
    output: dict[str, dict] = {}
    for row in opportunities:
        key = row.get("canonical_job_url") or f'{row.get("company_name", "").strip().lower()}|{row.get("role_title", "").strip().lower()}|{row.get("location", "").strip().lower()}'
        output[key] = row
    return output


async def _fetch_single_row(sb, table_name: str, user_id: str, row_id: str) -> dict:
    res = await asyncio.to_thread(
        lambda: sb.table(table_name)
        .select("*")
        .eq("id", row_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    row = (res.data or [None])[0]
    if not row:
        raise HTTPException(status_code=404, detail=f"{table_name} row not found")
    return row


@router.post("/search")
async def search_startup_hunt_opportunities(request: Request, body: StartupHuntSearchRequest):
    user_id = get_user_id(request)
    await _check_rate_limit_fail_open(user_id)
    existing = await _load_opportunity_map(user_id)
    results, overflow_results, filtered_out, parsed_strategy, configured_source_count, source_result_counts, source_diagnostics = await search_startup_hunt(body.model_dump(), existing)
    return {
        "results": results,
        "overflow_results": overflow_results,
        "filtered_out": filtered_out,
        "parsed_strategy": parsed_strategy,
        "configured_source_count": configured_source_count,
        "source_result_counts": source_result_counts,
        "source_diagnostics": source_diagnostics,
    }


@router.get("/opportunities")
async def list_startup_hunt_opportunities(request: Request):
    user_id = get_user_id(request)
    rows = await _load_opportunities(user_id)
    rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    return rows


@router.get("/contacts")
async def list_startup_hunt_contacts(request: Request, opportunity_id: str | None = None):
    user_id = get_user_id(request)
    sb = get_supabase()
    query = sb.table("startup_hunt_contacts").select("*").eq("user_id", user_id)
    if opportunity_id:
        query = query.eq("opportunity_id", opportunity_id)
    res = await asyncio.to_thread(lambda: query.execute())
    rows = res.data or []
    rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    return rows


@router.get("/artifact-counts")
async def get_artifact_counts(request: Request):
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("opportunity_artifacts")
        .select("opportunity_id")
        .eq("user_id", user_id)
        .not_.is_("opportunity_id", "null")
        .execute()
    )
    counts: dict[str, int] = {}
    for row in res.data or []:
        oid = row["opportunity_id"]
        counts[oid] = counts.get(oid, 0) + 1
    return counts


@router.get("/opportunities/{opportunity_id}/artifacts")
async def list_opportunity_artifacts(request: Request, opportunity_id: str):
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("opportunity_artifacts")
        .select("*")
        .eq("user_id", user_id)
        .eq("opportunity_id", opportunity_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


@router.post("/opportunities/{opportunity_id}/artifacts", status_code=201)
async def create_opportunity_artifact(request: Request, opportunity_id: str, body: dict):
    user_id = get_user_id(request)
    sb = get_supabase()
    artifact_type = body.get("artifact_type", "")
    if artifact_type not in {"resume_analysis", "cover_letter", "interview_prep"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Invalid artifact_type")
    row = {
        "user_id": user_id,
        "opportunity_id": opportunity_id,
        "artifact_type": artifact_type,
        "tool_used": body.get("tool_used", artifact_type),
        "content": body.get("content", ""),
        "metadata": body.get("metadata", {}),
    }
    res = await asyncio.to_thread(lambda: sb.table("opportunity_artifacts").insert(row).execute())
    return res.data[0] if res.data else {}


@router.delete("/opportunities/{opportunity_id}/artifacts/{artifact_id}", status_code=204)
async def delete_opportunity_artifact(request: Request, opportunity_id: str, artifact_id: str):
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("opportunity_artifacts")
        .delete()
        .eq("id", artifact_id)
        .eq("opportunity_id", opportunity_id)
        .eq("user_id", user_id)
        .select()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Artifact not found")


@router.post("/opportunities", status_code=201)
async def create_startup_hunt_opportunity(request: Request, body: StartupHuntOpportunityCreateRequest):
    user_id = get_user_id(request)
    sb = get_supabase()
    await _ensure_profile_exists(sb, user_id, request)
    payload = body.model_dump()

    direct_apply_url = str(body.direct_apply_url) if body.direct_apply_url else None
    canonical_job_url = str(body.canonical_job_url) if body.canonical_job_url else (canonicalize_url(direct_apply_url) if direct_apply_url else None)
    portal_job_url = str(body.portal_job_url) if body.portal_job_url else None
    company_website_url = str(body.company_website_url) if body.company_website_url else None
    company_careers_url = str(body.company_careers_url) if body.company_careers_url else None

    payload.update(
        {
            "direct_apply_url": direct_apply_url,
            "canonical_job_url": canonical_job_url,
            "portal_job_url": portal_job_url,
            "company_website_url": company_website_url,
            "company_careers_url": company_careers_url,
            "company_domain": payload.get("company_domain") or extract_domain(company_website_url or company_careers_url or direct_apply_url),
            "discovered_at": payload.get("discovered_at") or datetime.now(timezone.utc).isoformat(),
        }
    )

    existing_res = await asyncio.to_thread(
        lambda: sb.table("startup_hunt_opportunities")
        .select("*")
        .eq("user_id", user_id)
        .eq("company_name", payload["company_name"])
        .eq("role_title", payload["role_title"])
        .eq("location", payload["location"])
        .limit(1)
        .execute()
    )
    existing = (existing_res.data or [None])[0]

    tracker_id = existing.get("tracker_application_id") if existing else None
    if payload["opportunity_status"] == "applied":
        tracker_id = await _upsert_tracker_application(
            sb=sb,
            user_id=user_id,
            tracker_id=tracker_id,
            company=payload["company_name"],
            role=payload["role_title"],
            location=payload["location"],
        )

    company_id = await _upsert_company(sb, user_id, payload)
    db_payload = {
        **{k: v for k, v in payload.items() if k != "contacts"},
        "user_id": user_id,
        "tracker_application_id": tracker_id,
        "company_id": company_id,
    }

    if existing:
        await asyncio.to_thread(
            lambda: sb.table("startup_hunt_opportunities")
            .update(db_payload)
            .eq("id", existing["id"])
            .eq("user_id", user_id)
            .execute()
        )
        opportunity = await _fetch_single_row(sb, "startup_hunt_opportunities", user_id, existing["id"])
        await _replace_contacts(sb, user_id, opportunity["id"], payload.get("contacts", []), company_id)
    else:
        res = await asyncio.to_thread(lambda: sb.table("startup_hunt_opportunities").insert(db_payload).execute())
        created = (res.data or [None])[0]
        if not created:
            raise HTTPException(status_code=500, detail="Failed to create startup hunt opportunity")
        opportunity = await _fetch_single_row(sb, "startup_hunt_opportunities", user_id, created["id"])
        await _replace_contacts(sb, user_id, opportunity["id"], payload.get("contacts", []), company_id)
    return opportunity


@router.put("/opportunities/{opportunity_id}")
async def update_startup_hunt_opportunity(request: Request, opportunity_id: str, body: StartupHuntOpportunityUpdateRequest):
    user_id = get_user_id(request)
    sb = get_supabase()
    existing_res = await asyncio.to_thread(
        lambda: sb.table("startup_hunt_opportunities")
        .select("*")
        .eq("id", opportunity_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    existing = (existing_res.data or [None])[0]
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")

    updates = body.model_dump()
    updates["direct_apply_url"] = str(body.direct_apply_url) if body.direct_apply_url else existing.get("direct_apply_url")
    updates["canonical_job_url"] = str(body.canonical_job_url) if body.canonical_job_url else existing.get("canonical_job_url")

    if updates["opportunity_status"] == "applied":
        tracker_id = await _upsert_tracker_application(
            sb=sb,
            user_id=user_id,
            tracker_id=existing.get("tracker_application_id"),
            company=existing["company_name"],
            role=existing["role_title"],
            location=existing["location"],
        )
        updates["tracker_application_id"] = tracker_id

    await asyncio.to_thread(
        lambda: sb.table("startup_hunt_opportunities")
        .update(updates)
        .eq("id", opportunity_id)
        .eq("user_id", user_id)
        .execute()
    )
    return await _fetch_single_row(sb, "startup_hunt_opportunities", user_id, opportunity_id)


@router.delete("/opportunities/{opportunity_id}", status_code=204)
async def delete_startup_hunt_opportunity(request: Request, opportunity_id: str):
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("startup_hunt_opportunities")
        .delete()
        .eq("id", opportunity_id)
        .eq("user_id", user_id)
        .select()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Not found")


async def _upsert_company(sb, user_id: str, payload: dict) -> str:
    company_payload = payload.get("company_payload") or {}
    existing_res = await asyncio.to_thread(
        lambda: sb.table("startup_hunt_companies")
        .select("*")
        .eq("user_id", user_id)
        .eq("company_name", payload["company_name"])
        .limit(1)
        .execute()
    )
    existing = (existing_res.data or [None])[0]
    db_payload = {
        "user_id": user_id,
        "company_name": payload["company_name"],
        "company_domain": payload.get("company_domain"),
        "company_website_url": payload.get("company_website_url"),
        "company_careers_url": payload.get("company_careers_url"),
        "country": payload.get("country"),
        "city": company_payload.get("city"),
        "stage": company_payload.get("stage"),
        "company_size": company_payload.get("company_size"),
        "ai_relevance": company_payload.get("ai_relevance"),
        "english_friendly": bool(company_payload.get("english_friendly")),
        "relocation_support": company_payload.get("relocation_support"),
        "source_payload": company_payload,
    }
    if existing:
        await asyncio.to_thread(
            lambda: sb.table("startup_hunt_companies")
            .update(db_payload)
            .eq("id", existing["id"])
            .eq("user_id", user_id)
            .execute()
        )
        row = await _fetch_single_row(sb, "startup_hunt_companies", user_id, existing["id"])
    else:
        res = await asyncio.to_thread(lambda: sb.table("startup_hunt_companies").insert(db_payload).execute())
        created = (res.data or [None])[0]
        if not created:
            raise HTTPException(status_code=500, detail="Failed to create startup hunt company")
        row = await _fetch_single_row(sb, "startup_hunt_companies", user_id, created["id"])
    return row["id"]


async def _replace_contacts(sb, user_id: str, opportunity_id: str, contacts: list[dict], company_id: str | None) -> None:
    await asyncio.to_thread(
        lambda: sb.table("startup_hunt_contacts")
        .delete()
        .eq("user_id", user_id)
        .eq("opportunity_id", opportunity_id)
        .execute()
    )
    if not contacts:
        return
    rows = []
    for contact in contacts:
        rows.append(
            {
                "user_id": user_id,
                "opportunity_id": opportunity_id,
                "company_id": company_id,
                "name": contact.get("name"),
                "title": contact.get("title"),
                "contact_type": contact.get("contact_type"),
                "email": contact.get("email"),
                "email_confidence": contact.get("email_confidence"),
                "linkedin_url": contact.get("linkedin_url"),
                "source": contact.get("source"),
                "provider_chain": contact.get("provider_chain") or [],
            }
        )
    await asyncio.to_thread(lambda: sb.table("startup_hunt_contacts").insert(rows).execute())


async def _upsert_tracker_application(*, sb, user_id: str, tracker_id: str | None, company: str, role: str, location: str) -> str:
    tracker_payload = {
        "user_id": user_id,
        "company": company,
        "role": role,
        "applied_at": datetime.now(timezone.utc).date().isoformat(),
        "status": "Applied",
        "notes": f"Synced from Startup Hunt for {location}",
    }
    if tracker_id:
        await asyncio.to_thread(
            lambda: sb.table("job_applications")
            .update(tracker_payload)
            .eq("id", tracker_id)
            .eq("user_id", user_id)
            .execute()
        )
        updated = await _fetch_single_row(sb, "job_applications", user_id, tracker_id)
        if updated:
            return updated["id"]
    res = await asyncio.to_thread(lambda: sb.table("job_applications").insert(tracker_payload).execute())
    created = (res.data or [None])[0]
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create tracker application")
    created_row = await _fetch_single_row(sb, "job_applications", user_id, created["id"])
    return created_row["id"]
