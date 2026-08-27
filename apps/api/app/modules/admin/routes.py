"""Admin-only observability endpoints - read-only (Tier 1), consumed by the
separate apps/admin Next.js app. Every route is gated to profiles.role ==
'admin' via require_role - see app/modules/auth/service.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.service import require_role
from app.modules.admin import service

router = APIRouter(dependencies=[Depends(require_role("admin"))])


@router.get("/crawler/overview")
async def get_crawler_overview(db: AsyncSession = Depends(get_db)):
    return await service.get_crawler_overview(db)


@router.get("/crawler/companies")
async def list_companies(
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(default=service.DEFAULT_PAGE_SIZE, ge=1, le=service.MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    return await service.list_companies(db, status=status, search=search, limit=limit, offset=offset)


@router.get("/crawler/companies/{company_id}")
async def get_company_detail(company_id: str, db: AsyncSession = Depends(get_db)):
    return await service.get_company_detail(db, company_id)


@router.get("/crawler/jobs")
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    search: str | None = None,
    company_id: str | None = None,
    limit: int = Query(default=service.DEFAULT_PAGE_SIZE, ge=1, le=service.MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    return await service.list_jobs(db, search=search, company_id=company_id, limit=limit, offset=offset)


@router.get("/startup-scout/overview")
async def get_startup_scout_overview():
    return await service.get_startup_scout_overview()
