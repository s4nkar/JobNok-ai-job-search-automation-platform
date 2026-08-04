"""Recent job search endpoints and apply tracking."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from lib.config import settings
from lib.job_search import canonicalize_job_url, load_job_search_sources, search_jobs
from lib.redis_client import check_rate_limit
from lib.supabase_client import get_supabase, get_user_id
from models.schemas import (
    JobSearchApplicationCreateRequest,
    JobSearchApplicationUpdateRequest,
    JobSearchRequest,
)

router = APIRouter()


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


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


async def _load_user_job_search_applications(user_id: str) -> list[dict]:
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("job_search_applications")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return res.data or []


async def _load_user_applications_map(user_id: str) -> dict[str, dict]:
    rows = await _load_user_job_search_applications(user_id)
    return {row["job_url_canonical"]: row for row in rows if row.get("job_url_canonical")}


@router.post("/search")
async def search_recent_jobs(request: Request, body: JobSearchRequest):
    user_id = get_user_id(request)
    await _check_rate_limit_fail_open(user_id)

    user_applications = await _load_user_applications_map(user_id)
    configured_sources = load_job_search_sources()
    results, parsed_preferences = await search_jobs(body.model_dump(), user_applications)
    return {
        "results": results,
        "parsed_preferences": parsed_preferences,
        "configured_source_count": len(configured_sources),
    }


@router.get("/applications")
async def list_job_search_applications(request: Request):
    user_id = get_user_id(request)
    rows = await _load_user_job_search_applications(user_id)
    rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    return rows


@router.post("/applications", status_code=201)
async def create_job_search_application(request: Request, body: JobSearchApplicationCreateRequest):
    user_id = get_user_id(request)
    sb = get_supabase()

    payload = body.model_dump()
    payload["job_url"] = str(body.job_url)
    payload["job_url_canonical"] = canonicalize_job_url(str(body.job_url_canonical or body.job_url))

    existing_res = await asyncio.to_thread(
        lambda: sb.table("job_search_applications")
        .select("*")
        .eq("user_id", user_id)
        .eq("job_url_canonical", payload["job_url_canonical"])
        .limit(1)
        .execute()
    )
    existing = (existing_res.data or [None])[0]

    tracker_id = existing.get("tracker_application_id") if existing else None
    if payload["application_status"] == "applied":
        tracker_id = await _upsert_tracker_application(
            sb=sb,
            user_id=user_id,
            tracker_id=tracker_id,
            company=payload["company"],
            role=payload["role"],
            location=payload["location"],
            applied_at=payload.get("applied_at") or datetime.now(timezone.utc).isoformat(),
        )

    db_payload = {
        **payload,
        "user_id": user_id,
        "tracker_application_id": tracker_id,
        "discovered_at": existing.get("discovered_at") if existing else datetime.now(timezone.utc).isoformat(),
    }

    if payload["application_status"] == "applied" and not payload.get("applied_at"):
        db_payload["applied_at"] = datetime.now(timezone.utc).isoformat()

    if existing:
        res = await asyncio.to_thread(
            lambda: sb.table("job_search_applications")
            .update(db_payload)
            .eq("id", existing["id"])
            .eq("user_id", user_id)
            .select()
            .single()
            .execute()
        )
    else:
        res = await asyncio.to_thread(
            lambda: sb.table("job_search_applications")
            .insert(db_payload)
            .select()
            .single()
            .execute()
        )
    return res.data


@router.put("/applications/{application_id}")
async def update_job_search_application(request: Request, application_id: str, body: JobSearchApplicationUpdateRequest):
    user_id = get_user_id(request)
    sb = get_supabase()

    existing_res = await asyncio.to_thread(
        lambda: sb.table("job_search_applications")
        .select("*")
        .eq("id", application_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    existing = (existing_res.data or [None])[0]
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")

    updates = body.model_dump()
    if updates["application_status"] == "applied" and not updates.get("applied_at"):
        updates["applied_at"] = datetime.now(timezone.utc).isoformat()

    if updates["application_status"] == "applied":
        tracker_id = await _upsert_tracker_application(
            sb=sb,
            user_id=user_id,
            tracker_id=existing.get("tracker_application_id"),
            company=existing["company"],
            role=existing["role"],
            location=existing["location"],
            applied_at=updates.get("applied_at") or existing.get("applied_at") or datetime.now(timezone.utc).isoformat(),
        )
        updates["tracker_application_id"] = tracker_id

    res = await asyncio.to_thread(
        lambda: sb.table("job_search_applications")
        .update(updates)
        .eq("id", application_id)
        .eq("user_id", user_id)
        .select()
        .single()
        .execute()
    )
    return res.data


async def _upsert_tracker_application(
    *,
    sb,
    user_id: str,
    tracker_id: str | None,
    company: str,
    role: str,
    location: str,
    applied_at: str,
) -> str:
    tracker_payload = {
        "user_id": user_id,
        "company": company,
        "role": role,
        "applied_at": applied_at[:10] if applied_at else _today_iso(),
        "status": "Applied",
        "notes": f"Synced from Recent Job Search for {location}",
    }

    if tracker_id:
        res = await asyncio.to_thread(
            lambda: sb.table("job_applications")
            .update(tracker_payload)
            .eq("id", tracker_id)
            .eq("user_id", user_id)
            .select()
            .single()
            .execute()
        )
        if res.data:
            return res.data["id"]

    res = await asyncio.to_thread(
        lambda: sb.table("job_applications")
        .insert(tracker_payload)
        .select()
        .single()
        .execute()
    )
    return res.data["id"]
