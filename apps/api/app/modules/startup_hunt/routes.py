"""Startup Hunt v2 endpoints for startup-first opportunity discovery."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.cache import check_rate_limit
from app.core.security import get_current_user_id
from app.modules.startup_hunt.schemas import (
    StartupHuntOpportunityCreateRequest,
    StartupHuntOpportunityUpdateRequest,
    StartupHuntSearchRequest,
)
from app.modules.startup_hunt import service

router = APIRouter()


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


@router.post("/search")
async def search_startup_hunt_opportunities(
    request: Request, body: StartupHuntSearchRequest, db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    await _check_rate_limit_fail_open(user_id)
    return await service.search_startup_hunt_opportunities(db, user_id, body)


@router.get("/opportunities")
async def list_startup_hunt_opportunities(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    return await service.list_startup_hunt_opportunities(db, user_id)


@router.get("/opportunities/{opportunity_id}")
async def get_startup_hunt_opportunity(opportunity_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    return await service.get_startup_hunt_opportunity(db, user_id, opportunity_id)


@router.get("/contacts")
async def list_startup_hunt_contacts(
    request: Request, db: AsyncSession = Depends(get_db), opportunity_id: str | None = None
):
    user_id = await get_current_user_id(request, db)
    return await service.list_startup_hunt_contacts(db, user_id, opportunity_id)


@router.get("/artifact-counts")
async def get_artifact_counts(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    return await service.get_artifact_counts(db, user_id)


@router.get("/opportunities/{opportunity_id}/artifacts")
async def list_opportunity_artifacts(opportunity_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    return await service.list_opportunity_artifacts(db, user_id, opportunity_id)


@router.post("/opportunities/{opportunity_id}/artifacts", status_code=201)
async def create_opportunity_artifact(
    opportunity_id: str, request: Request, body: dict, db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    return await service.create_opportunity_artifact(db, user_id, opportunity_id, body)


@router.delete("/opportunities/{opportunity_id}/artifacts/{artifact_id}", status_code=204)
async def delete_opportunity_artifact(
    opportunity_id: str, artifact_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    await service.delete_opportunity_artifact(db, user_id, opportunity_id, artifact_id)


@router.post("/opportunities", status_code=201)
async def create_startup_hunt_opportunity(
    request: Request, body: StartupHuntOpportunityCreateRequest, db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    return await service.create_startup_hunt_opportunity(db, user_id, body)


@router.put("/opportunities/{opportunity_id}")
async def update_startup_hunt_opportunity(
    opportunity_id: str, request: Request, body: StartupHuntOpportunityUpdateRequest, db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    return await service.update_startup_hunt_opportunity(db, user_id, opportunity_id, body)


@router.delete("/opportunities/{opportunity_id}", status_code=204)
async def delete_startup_hunt_opportunity(opportunity_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    await service.delete_startup_hunt_opportunity(db, user_id, opportunity_id)
