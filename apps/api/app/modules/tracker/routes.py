"""Job application tracker CRUD endpoints."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.modules.tracker.schemas import ApplicationIn
from app.modules.tracker import service
from app.modules.usage.service import record_event as record_tool_usage

router = APIRouter()


@router.get("")
async def list_applications(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    return await service.list_applications(db, user_id)


@router.post("", status_code=201)
async def create_application(request: Request, body: ApplicationIn, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    await record_tool_usage(db, user_id, "tracker")
    return await service.create_application(db, user_id, body)


@router.put("/{app_id}")
async def update_application(
    request: Request, app_id: str, body: ApplicationIn, db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    return await service.update_application(db, user_id, app_id, body)


@router.delete("/{app_id}", status_code=204)
async def delete_application(request: Request, app_id: str, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    await service.delete_application(db, user_id, app_id)
