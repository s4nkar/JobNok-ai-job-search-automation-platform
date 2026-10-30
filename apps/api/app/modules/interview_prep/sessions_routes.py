"""Saved interview-prep kits — My Docs listing, fetch-one, and rename.

Creation/upsert happens inside routes.py's generation handler itself (auto-
save, see service.py::resolve_session) - there is no POST /save here
anymore. Included into interview_prep/routes.py's router (see the bottom of
that file), so these still arrive under the existing /api/ai prefix
main.py already registers - no changes needed there.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.services.cache import check_burst_limit
from app.modules.interview_prep import service as interview_prep_service
from app.modules.interview_prep.repository import InterviewPrepSessionRepository
from app.modules.interview_prep.schemas import (
    InterviewPrepSessionDetail,
    InterviewPrepSessionListResponse,
    InterviewPrepTitleUpdateRequest,
)

router = APIRouter()


def _detail_response(session) -> InterviewPrepSessionDetail:
    return InterviewPrepSessionDetail(
        id=str(session.id),
        title=session.title,
        job_description=session.job_description,
        company=session.company,
        role=session.role,
        result=session.result,
        created_at=session.created_at.isoformat(),
        source_opportunity_id=str(session.source_opportunity_id) if session.source_opportunity_id else None,
        source_application_id=str(session.source_application_id) if session.source_application_id else None,
    )


# ── GET /interview/sessions ────────────────────────────────────────
# Literal path, registered before the /interview/sessions/{id}-shaped
# dynamic route below - same FastAPI/Starlette registration-order gotcha
# resume_tailor/routes.py documents.

@router.get("/interview/sessions", response_model=InterviewPrepSessionListResponse)
async def list_interview_prep_sessions(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    try:
        burst_ok = await check_burst_limit(
            user_id, "interview_sessions_list", settings.rate_limit_burst_limit, settings.rate_limit_burst_window_seconds,
        )
    except Exception:
        burst_ok = True
    if not burst_ok:
        raise HTTPException(status_code=429, detail="Too many requests, please wait a few seconds and try again.")

    sessions = await interview_prep_service.list_sessions_for_docs_page(db, user_id)
    return InterviewPrepSessionListResponse(sessions=sessions)


# ── GET /interview/sessions/{session_id} ──────────────────────────

@router.get("/interview/sessions/{session_id}", response_model=InterviewPrepSessionDetail)
async def get_interview_prep_session(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    session = await InterviewPrepSessionRepository(db).get(user_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Saved interview kit not found.")
    return _detail_response(session)


# ── PATCH /interview/sessions/{session_id}/title ──────────────────

@router.patch("/interview/sessions/{session_id}/title")
async def rename_interview_prep_session(
    session_id: str, request: Request, body: InterviewPrepTitleUpdateRequest, db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    session_repo = InterviewPrepSessionRepository(db)
    session = await session_repo.get(user_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Saved interview kit not found.")

    try:
        burst_ok = await check_burst_limit(
            user_id, "interview_title", settings.rate_limit_burst_limit, settings.rate_limit_burst_window_seconds,
        )
    except Exception:
        burst_ok = True
    if not burst_ok:
        raise HTTPException(status_code=429, detail="Too many rename requests, please wait a few seconds and try again.")

    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title cannot be empty.")

    await session_repo.set_title(user_id, session_id, title)
    return {"title": title}
