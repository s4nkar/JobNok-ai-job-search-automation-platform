"""My Docs — lists every resume the user has generated (tailoring_sessions).

Included into resume_tailor/routes.py's router (see the bottom of that file),
so this still arrives under the existing /api/ai prefix main.py already
registers — no changes needed there.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.services.cache import check_burst_limit
from app.modules.resume_tailor import service as resume_tailor_service
from app.modules.resume_tailor.schemas import SessionListResponse

router = APIRouter()


@router.get("/tailor/sessions", response_model=SessionListResponse)
async def list_tailor_sessions(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    try:
        burst_ok = await check_burst_limit(
            user_id, "resume_tailor_sessions_list", settings.rate_limit_burst_limit, settings.rate_limit_burst_window_seconds,
        )
    except Exception:
        burst_ok = True
    if not burst_ok:
        raise HTTPException(status_code=429, detail="Too many requests — please wait a few seconds and try again.")

    sessions = await resume_tailor_service.list_sessions_for_docs_page(db, user_id)
    return SessionListResponse(sessions=sessions)
