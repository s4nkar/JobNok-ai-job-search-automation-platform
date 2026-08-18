"""Bulk email campaign management router.

Creates campaigns, enqueues recipients to the ARQ worker, and provides live status.
"""

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.modules.bulk_email.schemas import CreateCampaignRequest
from app.modules.bulk_email import service
from app.modules.usage.service import record_event as record_tool_usage
from app.workers.arq_worker import get_arq_pool

router = APIRouter()


@router.post("/campaign")
async def create_campaign(
    request: Request,
    body: CreateCampaignRequest,
    db: AsyncSession = Depends(get_db),
    arq_pool: ArqRedis = Depends(get_arq_pool),
):
    user_id = await get_current_user_id(request, db)
    await record_tool_usage(db, user_id, "bulk-email")
    return await service.create_campaign(db, user_id, body, arq_pool)


@router.get("/campaign/{campaign_id}/status")
async def get_campaign_status(request: Request, campaign_id: str, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    return await service.get_campaign_status(db, user_id, campaign_id)


@router.post("/campaign/{campaign_id}/pause")
async def pause_campaign(request: Request, campaign_id: str, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    await service.pause_campaign(db, user_id, campaign_id)
    return {"status": "paused"}
