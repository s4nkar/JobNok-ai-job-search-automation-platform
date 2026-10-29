"""Saved cover letters - explicit Save + My Docs listing + rename.

Included into cover_letter/routes.py's router (see the bottom of that file),
so these still arrive under the existing /api/ai prefix main.py already
registers - no changes needed there.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.services.cache import check_burst_limit
from app.modules.cover_letter import service as cover_letter_service
from app.modules.cover_letter.repository import CoverLetterSessionRepository
from app.modules.cover_letter.schemas import (
    CoverLetterSaveRequest,
    CoverLetterSessionDetail,
    CoverLetterSessionListResponse,
    CoverLetterTitleUpdateRequest,
)

router = APIRouter()


def _detail_response(session) -> CoverLetterSessionDetail:
    return CoverLetterSessionDetail(
        id=str(session.id),
        title=session.title,
        company=session.company,
        role=session.role,
        selling_points=session.selling_points,
        resume_text=session.resume_text,
        content=session.content,
        created_at=session.created_at.isoformat(),
        source_opportunity_id=str(session.source_opportunity_id) if session.source_opportunity_id else None,
        source_application_id=str(session.source_application_id) if session.source_application_id else None,
    )


# ── POST /cover-letter/save ────────────────────────────────────────
# Literal path, registered before any /cover-letter/sessions/{id}-shaped
# dynamic route below - same FastAPI/Starlette registration-order gotcha
# resume_tailor/routes.py documents (a dynamic {id} route would otherwise
# try to swallow a literal segment first).

@router.post("/cover-letter/save", response_model=CoverLetterSessionDetail)
async def save_cover_letter_session(request: Request, body: CoverLetterSaveRequest, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    try:
        burst_ok = await check_burst_limit(
            user_id, "cover_letter_save", settings.rate_limit_burst_limit, settings.rate_limit_burst_window_seconds,
        )
    except Exception:
        burst_ok = True
    if not burst_ok:
        raise HTTPException(status_code=429, detail="Too many requests, please wait a few seconds and try again.")

    source_opportunity_id = None
    if body.opportunity_id and await cover_letter_service.verify_opportunity_ownership(db, user_id, body.opportunity_id):
        source_opportunity_id = body.opportunity_id
    source_application_id = None
    if body.job_search_application_id and await cover_letter_service.verify_application_ownership(
        db, user_id, body.job_search_application_id
    ):
        source_application_id = body.job_search_application_id

    session = await CoverLetterSessionRepository(db).create_session(
        user_id,
        company=body.company,
        role=body.role,
        selling_points=body.selling_points,
        resume_text=body.resume_text,
        content=body.content,
        source_opportunity_id=source_opportunity_id,
        source_application_id=source_application_id,
    )
    return _detail_response(session)


# ── GET /cover-letter/sessions ─────────────────────────────────────

@router.get("/cover-letter/sessions", response_model=CoverLetterSessionListResponse)
async def list_cover_letter_sessions(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    try:
        burst_ok = await check_burst_limit(
            user_id, "cover_letter_sessions_list", settings.rate_limit_burst_limit, settings.rate_limit_burst_window_seconds,
        )
    except Exception:
        burst_ok = True
    if not burst_ok:
        raise HTTPException(status_code=429, detail="Too many requests, please wait a few seconds and try again.")

    sessions = await cover_letter_service.list_sessions_for_docs_page(db, user_id)
    return CoverLetterSessionListResponse(sessions=sessions)


# ── GET /cover-letter/sessions/{session_id} ───────────────────────

@router.get("/cover-letter/sessions/{session_id}", response_model=CoverLetterSessionDetail)
async def get_cover_letter_session(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    session = await CoverLetterSessionRepository(db).get(user_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Saved cover letter not found.")
    return _detail_response(session)


# ── PATCH /cover-letter/sessions/{session_id}/title ────────────────

@router.patch("/cover-letter/sessions/{session_id}/title")
async def rename_cover_letter_session(
    session_id: str, request: Request, body: CoverLetterTitleUpdateRequest, db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    session_repo = CoverLetterSessionRepository(db)
    session = await session_repo.get(user_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Saved cover letter not found.")

    try:
        burst_ok = await check_burst_limit(
            user_id, "cover_letter_title", settings.rate_limit_burst_limit, settings.rate_limit_burst_window_seconds,
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
