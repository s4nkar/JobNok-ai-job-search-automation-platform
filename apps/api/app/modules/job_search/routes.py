"""Recent job search endpoints and apply tracking."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.modules.job_search.schemas import (
    JobSearchApplicationCreateRequest,
    JobSearchApplicationUpdateRequest,
    JobSearchRequest,
)
from app.modules.job_search import service

router = APIRouter()


@router.post("/search")
async def search_recent_jobs(request: Request, body: JobSearchRequest, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    return await service.search_recent_jobs(db, user_id, body)


@router.get("/applications")
async def list_job_search_applications(
    request: Request,
    db: AsyncSession = Depends(get_db),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    user_id = await get_current_user_id(request, db)
    return await service.list_job_search_applications(db, user_id, limit=limit, offset=offset)


@router.get("/applications/{application_id}")
async def get_job_search_application(application_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    return await service.get_job_search_application(db, user_id, application_id)


@router.post("/applications", status_code=201)
async def create_job_search_application(
    request: Request, body: JobSearchApplicationCreateRequest, db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    return await service.create_job_search_application(db, user_id, body)


@router.put("/applications/{application_id}")
async def update_job_search_application(
    request: Request,
    application_id: str,
    body: JobSearchApplicationUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_current_user_id(request, db)
    return await service.update_job_search_application(db, user_id, application_id, body)


@router.delete("/applications/{application_id}", status_code=204)
async def delete_job_search_application(request: Request, application_id: str, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    await service.delete_job_search_application(db, user_id, application_id)
