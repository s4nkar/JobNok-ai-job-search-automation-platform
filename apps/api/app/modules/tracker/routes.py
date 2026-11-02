"""Job application tracker CRUD endpoints.

Not AI/scrape-costed, but every write (and the list read) still goes
through the shared burst-window guard - "every endpoint, not just the ones
that happen to call an LLM" is this codebase's established rate-limiting
convention (see docs/templates/production_hardening_playbook.md for the
same reasoning applied there). Creation additionally has a generous daily
quota as a storage-abuse ceiling.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.services.cache import check_burst_limit, check_rate_limit
from app.shared.utils import _rl_error
from app.modules.tracker.schemas import ApplicationIn
from app.modules.tracker import service
from app.modules.usage.service import record_event as record_tool_usage

router = APIRouter()


async def _enforce_burst(user_id: str, bucket: str) -> None:
    try:
        burst_ok = await check_burst_limit(
            user_id, bucket, settings.rate_limit_burst_limit, settings.rate_limit_burst_window_seconds,
        )
    except Exception:
        burst_ok = True
    if not burst_ok:
        raise HTTPException(status_code=429, detail="Too many requests, please wait a few seconds and try again.")


@router.get("")
async def list_applications(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    await _enforce_burst(user_id, "tracker_list")
    return await service.list_applications(db, user_id)


@router.post("", status_code=201)
async def create_application(request: Request, body: ApplicationIn, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    allowed, _ = await check_rate_limit(user_id, "tracker_create", settings.rate_limit_tracker_create_per_day)
    if not allowed:
        raise _rl_error("Tracker", settings.rate_limit_tracker_create_per_day)
    await _enforce_burst(user_id, "tracker_create")
    await record_tool_usage(db, user_id, "tracker")
    return await service.create_application(db, user_id, body)


@router.put("/{app_id}")
async def update_application(
    request: Request, app_id: str, body: ApplicationIn, db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    await _enforce_burst(user_id, "tracker_update")
    return await service.update_application(db, user_id, app_id, body)


@router.delete("/{app_id}", status_code=204)
async def delete_application(request: Request, app_id: str, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    await _enforce_burst(user_id, "tracker_delete")
    await service.delete_application(db, user_id, app_id)
