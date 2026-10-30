"""DB touchpoints for interview_prep's saved-session feature (My Docs).

Ownership checks are duplicated from resume_tailor/service.py rather than
imported cross-module - same independence reasoning cover_letter's own
service.py documents (each tool owns its own copy rather than depending on
another tool's internals).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.interview_prep.models import InterviewPrepSession
from app.modules.interview_prep.repository import InterviewPrepSessionRepository
from app.modules.interview_prep.schemas import InterviewPrepRequest, InterviewPrepSessionSummary
from app.modules.job_search.models import JobSearchApplication
from app.modules.startup_hunt.models import StartupHuntOpportunity


async def verify_opportunity_ownership(db: AsyncSession, user_id: str, opportunity_id: str) -> bool:
    """True if opportunity_id exists and belongs to user_id. Never trust a
    client-supplied id without re-checking ownership."""
    row = (
        await db.execute(
            select(StartupHuntOpportunity.id).where(
                StartupHuntOpportunity.id == opportunity_id, StartupHuntOpportunity.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def verify_application_ownership(db: AsyncSession, user_id: str, application_id: str) -> bool:
    """True if application_id exists and belongs to user_id."""
    row = (
        await db.execute(
            select(JobSearchApplication.id).where(
                JobSearchApplication.id == application_id, JobSearchApplication.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def resolve_session(
    db: AsyncSession, user_id: str, body: InterviewPrepRequest, result: dict[str, Any],
) -> InterviewPrepSession:
    """Creates or upserts the InterviewPrepSession a generation belongs to.
    Called after the result has already been generated and validated (this
    endpoint isn't streaming, so - unlike cover_letter - there's no need to
    create a placeholder row before the AI call just to get an id early).

    Resolution order: a job-linked existing session (one row per job,
    regardless of browser visit - "only one saved interview kit per job")
    takes priority over session_id (one row per ad-hoc browser visit, used
    only when there's no job to key off of). A new row is created only
    when neither applies.
    """
    repo = InterviewPrepSessionRepository(db)

    source_opportunity_id = None
    source_application_id = None
    if body.opportunity_id and await verify_opportunity_ownership(db, user_id, body.opportunity_id):
        source_opportunity_id = body.opportunity_id
    elif body.job_search_application_id and await verify_application_ownership(db, user_id, body.job_search_application_id):
        source_application_id = body.job_search_application_id

    existing = None
    if source_opportunity_id or source_application_id:
        existing = await repo.get_by_source(
            user_id, source_opportunity_id=source_opportunity_id, source_application_id=source_application_id,
        )
    elif body.session_id:
        existing = await repo.get(user_id, body.session_id)

    if existing is not None:
        return await repo.update(
            user_id, str(existing.id),
            job_description=body.job_description, company=body.company, role=body.role, result=result,
        )
    return await repo.create_session(
        user_id,
        job_description=body.job_description, company=body.company, role=body.role, result=result,
        source_opportunity_id=source_opportunity_id, source_application_id=source_application_id,
    )


async def apply_regenerated_answer(
    db: AsyncSession, user_id: str, session_id: str, question_index: int, regenerated: dict[str, Any],
) -> None:
    """Writes a regenerated answer_framework/tips back into the saved
    session's result.questions[question_index] - otherwise a saved kit
    would silently drift out of sync with what the user sees after a
    regenerate. Silently no-ops if the session or index doesn't exist
    (e.g. a stale session_id from a since-deleted save) rather than
    failing the regenerate response the user is actually waiting on."""
    repo = InterviewPrepSessionRepository(db)
    session = await repo.get(user_id, session_id)
    if session is None:
        return
    questions = list((session.result or {}).get("questions") or [])
    if not (0 <= question_index < len(questions)):
        return
    questions[question_index] = {**questions[question_index], **regenerated}
    updated_result = {**session.result, "questions": questions}
    await repo.update(user_id, session_id, result=updated_result)


def _session_display_label(session: InterviewPrepSession) -> str:
    """Fallback chain: user-set title, then a real company+role (literal
    form fields when known), then the AI-inferred role_family from the
    saved result (a plain pasted JD often has neither), then a generic
    label. No is_ai_matched flag needed like resume_tailor's equivalent -
    role_family is only ever used as a last-resort label here, never
    presented as if it were a confirmed job match."""
    if session.title:
        return session.title
    if session.company and session.role:
        return f"{session.role} at {session.company}"
    role_family = ((session.result or {}).get("role_assessment") or {}).get("role_family")
    if role_family:
        return f"{role_family} Interview Kit"
    return "Interview Prep Kit"


async def list_sessions_for_docs_page(db: AsyncSession, user_id: str) -> list[InterviewPrepSessionSummary]:
    """Powers the "My Docs" page - every saved interview kit, most recent
    first."""
    sessions = await InterviewPrepSessionRepository(db).list(user_id, order_by=InterviewPrepSession.created_at.desc())
    return [
        InterviewPrepSessionSummary(
            id=str(s.id),
            title=s.title,
            display_label=_session_display_label(s),
            question_count=len((s.result or {}).get("questions") or []),
            created_at=s.created_at.isoformat(),
            source_opportunity_id=str(s.source_opportunity_id) if s.source_opportunity_id else None,
            source_application_id=str(s.source_application_id) if s.source_application_id else None,
        )
        for s in sessions
    ]
