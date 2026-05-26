"""Startup Scout REST endpoints for company discovery and contact enrichment."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, field_validator

from lib.redis_client import check_rate_limit
from lib.startup_scout import (
    apollo_search_contacts,
    enrich_linkedin_url,
    search_startups,
    verify_contact,
    web_search_contacts,
)
from lib.supabase_client import get_supabase, get_user_id
from routers.startup_hunt import _ensure_profile_exists

log = logging.getLogger(__name__)
router = APIRouter()

RATE_LIMIT_SCOUT_SEARCH_PER_DAY = 20
RATE_LIMIT_SCOUT_CRAWL_PER_DAY = 30
MIN_VERIFIED_CONTACTS = 2

# In-process cancel flags keyed by company_id.
# Set to True by the /stop endpoint; _run_crawl checks between each contact save.
_cancel_flags: dict[str, bool] = {}


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
    def validate_website(cls, value: str) -> str:
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("website must be an http or https URL")
        return value


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


async def _save_contact(sb, company_id: str, user_id: str, contact: dict) -> None:
    row = {
        "company_id": company_id,
        "user_id": user_id,
        "name": contact.get("name"),
        "title": contact.get("title"),
        "email": contact.get("email"),
        "linkedin_url": contact.get("linkedin_url"),
        "source": contact.get("source"),
        "source_url": contact.get("source_url") or None,
        "confidence": float(contact.get("confidence") or 0),
    }
    try:
        await asyncio.to_thread(
            lambda: sb.table("startup_scout_contacts").insert(row).execute()
        )
    except Exception:
        # source_url / is_verified columns may not exist yet (migration not run).
        # Retry with only the baseline columns so contacts are never lost.
        baseline = {k: v for k, v in row.items() if k not in ("source_url",)}
        await asyncio.to_thread(
            lambda: sb.table("startup_scout_contacts").insert(baseline).execute()
        )


async def _load_saved_contacts(sb, company_id: str) -> list[dict]:
    res = await asyncio.to_thread(
        lambda: sb.table("startup_scout_contacts")
        .select("*")
        .eq("company_id", company_id)
        .execute()
    )
    return res.data or []


async def _enrich_missing_linkedin(sb, company_id: str, company_name: str) -> None:
    res = await asyncio.to_thread(
        lambda: sb.table("startup_scout_contacts")
        .select("id, name, linkedin_url")
        .eq("company_id", company_id)
        .execute()
    )
    needs_linkedin = [
        row for row in (res.data or [])
        if not row.get("linkedin_url") and row.get("name")
    ]
    log.info(
        "Stage 1.5: enriching LinkedIn for %d contacts without a URL",
        len(needs_linkedin),
    )

    for row in needs_linkedin:
        if _cancel_flags.get(company_id):
            break
        await asyncio.sleep(1.5)
        linkedin_url = await enrich_linkedin_url(row["name"], company_name)
        if not linkedin_url:
            continue
        try:
            await asyncio.to_thread(
                lambda url=linkedin_url, rid=row["id"]: (
                    sb.table("startup_scout_contacts")
                    .update({"linkedin_url": url})
                    .eq("id", rid)
                    .execute()
                )
            )
            log.info("Stage 1.5: linked %s -> %s", row["name"], linkedin_url[:80])
        except Exception as enrich_exc:
            log.warning(
                "Stage 1.5 LinkedIn update failed for %s: %s",
                row["name"], enrich_exc,
            )


async def _verify_saved_contacts(sb, company_id: str, company_name: str) -> int:
    saved_rows = await _load_saved_contacts(sb, company_id)
    log.info("Stage 2: verifying %d contacts for %r", len(saved_rows), company_name)

    for row in saved_rows:
        if _cancel_flags.get(company_id):
            break
        contact_name = row.get("name") or ""
        if not contact_name:
            continue

        await asyncio.sleep(1.5)
        is_verified, verification_url = await verify_contact(
            contact_name=contact_name,
            company_name=company_name,
            original_source_url=row.get("source_url") or "",
        )

        try:
            await asyncio.to_thread(
                lambda verified=is_verified, url=verification_url, rid=row["id"]: (
                    sb.table("startup_scout_contacts")
                    .update({"is_verified": verified, "verification_url": url})
                    .eq("id", rid)
                    .execute()
                )
            )
        except Exception as verify_exc:
            # Gracefully skip if column doesn't exist yet (pre-migration).
            log.warning(
                "Stage 2 update failed for contact %s (run migration?): %s",
                row["id"], verify_exc,
            )

    refreshed_rows = await _load_saved_contacts(sb, company_id)
    verified_count = sum(1 for row in refreshed_rows if row.get("is_verified") is True)
    log.info("Stage 2: %d verified contacts for %r", verified_count, company_name)
    return verified_count


async def _supplement_with_apollo(
    sb,
    company_id: str,
    user_id: str,
    company_name: str,
) -> int:
    existing_rows = await _load_saved_contacts(sb, company_id)
    seen_names = {
        (row.get("name") or "").strip().lower()
        for row in existing_rows
        if (row.get("name") or "").strip()
    }
    seen_linkedin_urls = {
        (row.get("linkedin_url") or "").strip().rstrip("/").lower()
        for row in existing_rows
        if (row.get("linkedin_url") or "").strip()
    }
    seen_emails = {
        (row.get("email") or "").strip().lower()
        for row in existing_rows
        if (row.get("email") or "").strip()
    }

    apollo_contacts = await apollo_search_contacts(company_name)
    imported = 0
    for contact in apollo_contacts:
        if _cancel_flags.get(company_id):
            break

        name_key = (contact.get("name") or "").strip().lower()
        linkedin_key = (contact.get("linkedin_url") or "").strip().rstrip("/").lower()
        email_key = (contact.get("email") or "").strip().lower()

        is_duplicate = (
            (name_key and name_key in seen_names)
            or (linkedin_key and linkedin_key in seen_linkedin_urls)
            or (email_key and email_key in seen_emails)
        )
        if is_duplicate:
            continue

        await _save_contact(sb, company_id, user_id, contact)
        imported += 1

        if name_key:
            seen_names.add(name_key)
        if linkedin_key:
            seen_linkedin_urls.add(linkedin_key)
        if email_key:
            seen_emails.add(email_key)

    log.info("Apollo supplement: imported %d new contacts for %r", imported, company_name)
    return imported


async def _run_crawl(company_id: str, user_id: str, company_name: str) -> None:
    """Crawl contacts for a company, saving each one immediately."""
    sb = get_supabase()
    _cancel_flags.pop(company_id, None)

    await asyncio.to_thread(
        lambda: sb.table("startup_scout_companies")
        .update({"crawl_status": "crawling"})
        .eq("id", company_id)
        .eq("user_id", user_id)
        .execute()
    )

    await asyncio.to_thread(
        lambda: sb.table("startup_scout_contacts")
        .delete()
        .eq("company_id", company_id)
        .execute()
    )

    contacts_saved = 0
    crawl_errored = False

    try:
        web_contacts = await web_search_contacts(company_name)
        for contact in web_contacts:
            if _cancel_flags.get(company_id):
                break
            await _save_contact(sb, company_id, user_id, contact)
            contacts_saved += 1

        if contacts_saved == 0 and not _cancel_flags.get(company_id):
            apollo_contacts = await apollo_search_contacts(company_name)
            for contact in apollo_contacts:
                if _cancel_flags.get(company_id):
                    break
                await _save_contact(sb, company_id, user_id, contact)
                contacts_saved += 1

        verified_contacts = 0
        if contacts_saved > 0 and not _cancel_flags.get(company_id):
            await _enrich_missing_linkedin(sb, company_id, company_name)
            verified_contacts = await _verify_saved_contacts(sb, company_id, company_name)

        if (
            contacts_saved > 0
            and verified_contacts < MIN_VERIFIED_CONTACTS
            and not _cancel_flags.get(company_id)
        ):
            log.info(
                "Apollo supplement: only %d verified contacts for %r, fetching Apollo",
                verified_contacts, company_name,
            )
            imported_count = await _supplement_with_apollo(
                sb, company_id, user_id, company_name
            )
            contacts_saved += imported_count
            if imported_count > 0 and not _cancel_flags.get(company_id):
                await _enrich_missing_linkedin(sb, company_id, company_name)
                await _verify_saved_contacts(sb, company_id, company_name)

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
    """Signal a running crawl to stop after its current contact."""
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
