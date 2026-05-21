"""Startup Scout REST endpoints — company discovery + contact enrichment."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, field_validator

from lib.redis_client import check_rate_limit
from lib.startup_scout import apollo_search_contacts, search_startups, web_search_contacts
from lib.supabase_client import get_supabase, get_user_id
from routers.startup_hunt import _ensure_profile_exists

log = logging.getLogger(__name__)
router = APIRouter()

RATE_LIMIT_SCOUT_SEARCH_PER_DAY = 20
RATE_LIMIT_SCOUT_CRAWL_PER_DAY = 30

# In-process cancel flags keyed by company_id.
# Set to True by the /stop endpoint; _run_crawl checks between each contact save.
_cancel_flags: dict[str, bool] = {}


# ── Request models ───────────────────────────────────────────────────────────

class ScoutSearchRequest(BaseModel):
    location: str
    funding_stages: list[str] = []
    industry: str = ""
    size_range: str = ""
    limit: int = 50


class SaveCompanyRequest(BaseModel):
    name: str
    description: str = ""
    what_they_do: str = ""
    funding_stage: str = ""
    size_range: str = ""
    location: str = ""
    website: str = ""
    linkedin_url: str = ""
    source: str = "web_scrape"

    @field_validator("website")
    @classmethod
    def validate_website(cls, v: str) -> str:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("website must be an http or https URL")
        return v


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _rate_check(user_id: str, action: str, limit: int) -> None:
    try:
        allowed, _ = await check_rate_limit(user_id, action, limit)
    except Exception:
        return  # fail open if Redis is down
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit of {limit} reached for {action}. Resets at midnight UTC.",
        )


async def _get_company_or_404(sb, company_id: str, user_id: str) -> dict:
    res = await asyncio.to_thread(
        lambda: sb.table("startup_scout_companies")
        .select("*")
        .eq("id", company_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    row = (res.data or [None])[0]
    if not row:
        raise HTTPException(status_code=404, detail="Company not found")
    return row


async def _save_contact(sb, company_id: str, user_id: str, c: dict) -> None:
    row = {
        "company_id": company_id,
        "user_id": user_id,
        "name": c.get("name"),
        "title": c.get("title"),
        "email": c.get("email"),
        "linkedin_url": c.get("linkedin_url"),
        "source": c.get("source"),
        "confidence": float(c.get("confidence") or 0),
    }
    await asyncio.to_thread(
        lambda: sb.table("startup_scout_contacts").insert(row).execute()
    )


# ── Background crawl task ────────────────────────────────────────────────────

async def _run_crawl(company_id: str, user_id: str, company_name: str) -> None:
    """Crawl contacts for a company, saving each one immediately.

    Checks _cancel_flags[company_id] between each save so the /stop endpoint
    can halt the crawl mid-way while preserving contacts already written.
    """
    sb = get_supabase()
    _cancel_flags.pop(company_id, None)

    # Mark as crawling
    await asyncio.to_thread(
        lambda: sb.table("startup_scout_companies")
        .update({"crawl_status": "crawling"})
        .eq("id", company_id)
        .eq("user_id", user_id)
        .execute()
    )

    # Delete any contacts from a previous crawl (fresh start)
    await asyncio.to_thread(
        lambda: sb.table("startup_scout_contacts")
        .delete()
        .eq("company_id", company_id)
        .execute()
    )

    contacts_saved = 0
    crawl_errored = False

    try:
        # Phase 1: web search (DuckDuckGo/Bing, no API key)
        web_contacts = await web_search_contacts(company_name)
        for c in web_contacts:
            if _cancel_flags.get(company_id):
                break
            await _save_contact(sb, company_id, user_id, c)
            contacts_saved += 1

        # Phase 2: Apollo fallback — only if web found nothing and not cancelled
        if contacts_saved == 0 and not _cancel_flags.get(company_id):
            apollo_contacts = await apollo_search_contacts(company_name)
            for c in apollo_contacts:
                if _cancel_flags.get(company_id):
                    break
                await _save_contact(sb, company_id, user_id, c)
                contacts_saved += 1

    except Exception as exc:
        log.warning("Crawl error for company %s: %s", company_name, exc)
        crawl_errored = True

    finally:
        _cancel_flags.pop(company_id, None)

    if crawl_errored:
        final_status = "failed"
    elif contacts_saved > 0:
        final_status = "enriched"
    else:
        final_status = "partial"

    await asyncio.to_thread(
        lambda: sb.table("startup_scout_companies")
        .update({"crawl_status": final_status})
        .eq("id", company_id)
        .eq("user_id", user_id)
        .execute()
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/search")
async def scout_search(req: ScoutSearchRequest, request: Request):
    """Phase A: discover startups matching location/stage/industry."""
    user_id = get_user_id(request)
    await _rate_check(user_id, "startup_scout_search", RATE_LIMIT_SCOUT_SEARCH_PER_DAY)

    if not req.location.strip():
        raise HTTPException(status_code=422, detail="location is required")

    result = await search_startups(
        location=req.location.strip(),
        funding_stages=req.funding_stages,
        industry=req.industry.strip(),
        size_range=req.size_range.strip(),
        limit=req.limit,
    )
    companies = result["companies"]
    return {"companies": companies, "count": len(companies), "meta": result["meta"]}


@router.post("/companies")
async def save_company(req: SaveCompanyRequest, request: Request):
    """Save a discovered company to the Startup Scout tracker."""
    user_id = get_user_id(request)
    sb = get_supabase()
    await _ensure_profile_exists(sb, user_id, request)

    if not req.name.strip():
        raise HTTPException(status_code=422, detail="name is required")

    row = {
        "user_id": user_id,
        "name": req.name.strip(),
        "description": req.description,
        "what_they_do": req.what_they_do,
        "funding_stage": req.funding_stage,
        "size_range": req.size_range,
        "location": req.location,
        "website": req.website,
        "linkedin_url": req.linkedin_url,
        "source": req.source,
        "crawl_status": "pending",
    }
    res = await asyncio.to_thread(
        lambda: sb.table("startup_scout_companies").insert(row).execute()
    )
    created = (res.data or [{}])[0]
    return created


@router.get("/companies")
async def list_companies(request: Request):
    """List all saved Startup Scout companies for the current user."""
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("startup_scout_companies")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


@router.get("/companies/{company_id}")
async def get_company(company_id: str, request: Request):
    """Get a single company (used to poll crawl_status)."""
    user_id = get_user_id(request)
    sb = get_supabase()
    return await _get_company_or_404(sb, company_id, user_id)


@router.delete("/companies/{company_id}")
async def delete_company(company_id: str, request: Request):
    """Delete a saved company (cascades to contacts)."""
    user_id = get_user_id(request)
    # Cancel any running crawl first
    _cancel_flags[company_id] = True
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("startup_scout_companies")
        .delete()
        .eq("id", company_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"deleted": True}


@router.post("/companies/{company_id}/crawl")
async def start_crawl(
    company_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Trigger Phase B: crawl contacts for a saved company."""
    user_id = get_user_id(request)
    await _rate_check(user_id, "startup_scout_crawl", RATE_LIMIT_SCOUT_CRAWL_PER_DAY)

    sb = get_supabase()
    company = await _get_company_or_404(sb, company_id, user_id)

    if company["crawl_status"] == "crawling":
        raise HTTPException(status_code=409, detail="Crawl already in progress")

    background_tasks.add_task(_run_crawl, company_id, user_id, company["name"])
    return {"status": "crawl_started", "company_id": company_id}


@router.post("/companies/{company_id}/stop")
async def stop_crawl(company_id: str, request: Request):
    """Signal a running crawl to stop after its current contact.

    Contacts saved before the stop signal are preserved.
    Status will be set to 'enriched' or 'partial' by _run_crawl when it exits.
    """
    user_id = get_user_id(request)
    sb = get_supabase()
    company = await _get_company_or_404(sb, company_id, user_id)

    if company["crawl_status"] != "crawling":
        raise HTTPException(status_code=409, detail="No crawl in progress")

    _cancel_flags[company_id] = True
    return {"status": "stop_requested", "company_id": company_id}


@router.get("/companies/{company_id}/contacts")
async def get_contacts(company_id: str, request: Request):
    """Get enriched contacts for a saved company."""
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("startup_scout_contacts")
        .select("*")
        .eq("company_id", company_id)
        .eq("user_id", user_id)
        .order("confidence", desc=True)
        .execute()
    )
    return res.data or []
