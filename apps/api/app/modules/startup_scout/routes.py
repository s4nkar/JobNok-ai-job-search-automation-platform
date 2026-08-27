"""Startup Scout REST endpoints for company discovery and contact enrichment."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.cache import check_burst_limit, check_rate_limit
from app.core.security import get_current_user_id
from app.modules.startup_scout.schemas import ScoutSearchRequest, SaveCompanyRequest
from app.modules.startup_scout import service
from app.modules.usage.service import record_event as record_tool_usage

router = APIRouter()

RATE_LIMIT_SCOUT_SEARCH_PER_DAY = 20
RATE_LIMIT_SCOUT_CRAWL_PER_DAY = 30


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


async def _burst_check(user_id: str, action: str) -> None:
    """Catches a double-clicked search button or a retry loop with no
    backoff - the daily quota alone doesn't cap arrival rate, only total
    volume, so a rapid-fire burst still pays full DDG-scraping cost per
    request regardless of whether it's request #1 or #20 of the day. Same
    generic primitive/settings job_search uses (see
    job_search/service.py::_check_rate_limit_fail_open) - not
    startup-scout-specific plumbing."""
    try:
        burst_ok = await check_burst_limit(
            user_id, action, settings.rate_limit_burst_limit, settings.rate_limit_burst_window_seconds
        )
    except Exception:
        burst_ok = True  # fail open if Redis is down
    if not burst_ok:
        raise HTTPException(status_code=429, detail="Searching too quickly - please wait a few seconds and try again.")


@router.post("/search")
async def scout_search(req: ScoutSearchRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Phase A: discover startups matching location/stage/industry."""
    user_id = await get_current_user_id(request, db)
    await _burst_check(user_id, "startup_scout_search")
    await _rate_check(user_id, "startup_scout_search", RATE_LIMIT_SCOUT_SEARCH_PER_DAY)
    await record_tool_usage(db, user_id, "startup-scout")

    if not req.location.strip():
        raise HTTPException(status_code=422, detail="location is required")

    result = await service.search_startups(
        db,
        location=req.location.strip(),
        funding_stages=req.funding_stages,
        industry=req.industry.strip(),
        limit=req.limit,
    )
    companies = result["companies"]
    return {"companies": companies, "count": len(companies), "meta": result["meta"]}


@router.post("/companies")
async def save_company(req: SaveCompanyRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Save a discovered company to the Startup Scout tracker."""
    user_id = await get_current_user_id(request, db)
    return await service.save_company(db, user_id, req)


@router.get("/companies")
async def list_companies(request: Request, db: AsyncSession = Depends(get_db)):
    """List all saved Startup Scout companies for the current user."""
    user_id = await get_current_user_id(request, db)
    return await service.list_companies(db, user_id)


@router.get("/companies/{company_id}")
async def get_company(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get a single company (used to poll crawl_status)."""
    user_id = await get_current_user_id(request, db)
    return await service.get_company_or_404(db, user_id, company_id)


@router.delete("/companies/{company_id}")
async def delete_company(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Delete a saved company (cascades to contacts)."""
    user_id = await get_current_user_id(request, db)
    await service.delete_company(db, user_id, company_id)
    return {"deleted": True}


@router.post("/companies/{company_id}/crawl")
async def start_crawl(
    company_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger Phase B: crawl contacts for a saved company."""
    user_id = await get_current_user_id(request, db)
    await _rate_check(user_id, "startup_scout_crawl", RATE_LIMIT_SCOUT_CRAWL_PER_DAY)

    company = await service.start_crawl(db, user_id, company_id)

    background_tasks.add_task(service.run_crawl, company_id, user_id, company["name"])
    return {"status": "crawl_started", "company_id": company_id}


@router.post("/companies/{company_id}/stop")
async def stop_crawl(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Signal a running crawl to stop after its current contact."""
    user_id = await get_current_user_id(request, db)
    await service.stop_crawl(db, user_id, company_id)
    return {"status": "stop_requested", "company_id": company_id}


@router.get("/companies/{company_id}/contacts")
async def get_contacts(company_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get enriched contacts for a saved company."""
    user_id = await get_current_user_id(request, db)
    return await service.get_contacts(db, user_id, company_id)
