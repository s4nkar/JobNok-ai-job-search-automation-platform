"""Email template CRUD endpoints.

Not AI/scrape-costed, but every write (and the list read) still goes
through the shared burst-window guard - "every endpoint, not just the ones
that happen to call an LLM" is this codebase's established rate-limiting
convention (see docs/templates/production_hardening_playbook.md). Creation
additionally has a generous daily quota as a storage-abuse ceiling.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.services.cache import check_burst_limit, check_rate_limit
from app.shared.utils import _rl_error
from app.modules.templates.schemas import TemplateIn, TemplateUpdate
from app.modules.templates import service
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
async def list_templates(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    await _enforce_burst(user_id, "templates_list")
    return await service.list_templates(db, user_id)


@router.post("", status_code=201)
async def create_template(request: Request, body: TemplateIn, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    allowed, _ = await check_rate_limit(user_id, "templates_create", settings.rate_limit_templates_create_per_day)
    if not allowed:
        raise _rl_error("Templates", settings.rate_limit_templates_create_per_day)
    await _enforce_burst(user_id, "templates_create")
    await record_tool_usage(db, user_id, "templates")
    return await service.create_template(db, user_id, body)


@router.put("/{template_id}")
async def update_template(
    request: Request, template_id: str, body: TemplateUpdate, db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    await _enforce_burst(user_id, "templates_update")
    return await service.update_template(db, user_id, template_id, body)


@router.delete("/{template_id}", status_code=204)
async def delete_template(request: Request, template_id: str, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    await _enforce_burst(user_id, "templates_delete")
    await service.delete_template(db, user_id, template_id)


@router.post("/{template_id}/use")
async def use_template(request: Request, template_id: str, db: AsyncSession = Depends(get_db)):
    """Called when the user copies a filled-in template, to atomically bump
    use_count - see service.py::increment_use_count for why this is its own
    endpoint rather than a client-computed value passed to PUT."""
    user_id = await get_current_user_id(request, db)
    await _enforce_burst(user_id, "templates_use")
    return await service.increment_use_count(db, user_id, template_id)
