"""Email campaign read endpoints (create/status/pause live in routes.py)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_user_id
from app.modules.bulk_email import service

router = APIRouter()


@router.get("")
async def list_campaigns(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    return await service.list_campaigns(db, user_id)


@router.get("/{campaign_id}/recipients")
async def list_recipients(request: Request, campaign_id: str, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    return await service.list_recipients(db, user_id, campaign_id)
