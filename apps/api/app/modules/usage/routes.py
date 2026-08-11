"""Read-only endpoint for the dashboard's tool usage widget."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.modules.usage import service

router = APIRouter()


@router.get("/tools")
async def list_tool_usage(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    return await service.get_summary(db, user_id)
