"""DB touchpoints for cover_letter's saved-session feature (My Docs).

Ownership checks are duplicated from resume_tailor/service.py rather than
imported cross-module - keeps cover_letter independent of resume_tailor the
same way resume_tailor is independent of startup_hunt/job_search (it imports
their models for ownership checks, never their service functions).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cover_letter.models import CoverLetterSession
from app.modules.cover_letter.repository import CoverLetterSessionRepository
from app.modules.cover_letter.schemas import CoverLetterRequest, CoverLetterSessionSummary
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


async def resolve_session(db: AsyncSession, user_id: str, body: CoverLetterRequest) -> CoverLetterSession:
    """Creates or upserts the CoverLetterSession a generation belongs to,
    with placeholder content, BEFORE any AI call - so its id is known up
    front (routes.py hands it back via an X-Session-Id response header,
    since the generation endpoint streams and can't return it in the JSON
    body the way resume_tailor/interview_prep do).

    Resolution order: a job-linked existing session (one row per job,
    regardless of browser visit - "only one saved cover letter per job")
    takes priority over session_id (one row per ad-hoc browser visit, used
    only when there's no job to key off of). A new row is created only
    when neither applies. Commits immediately so the row is durable even
    if generation fails before the final content update.

    Lives here (not routes.py) specifically so it stays importable/testable
    without routes.py's WeasyPrint-importing rendering.py in the chain -
    same isolation reasoning as this module's own text.py.
    """
    repo = CoverLetterSessionRepository(db)

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
        session = await repo.update(
            user_id, str(existing.id),
            company=body.company, role=body.role, selling_points=body.selling_points,
            resume_text=body.resume_text, content="",
        )
    else:
        session = await repo.create_session(
            user_id,
            company=body.company, role=body.role, selling_points=body.selling_points,
            resume_text=body.resume_text, content="",
            source_opportunity_id=source_opportunity_id, source_application_id=source_application_id,
        )
    await db.commit()
    return session


def _session_display_label(session: CoverLetterSession) -> str:
    """Simpler than resume_tailor's version - company/role are always
    literal form fields on a cover letter session (never AI-guessed), so
    there's no opportunity/application fallback lookup or is_ai_matched
    ambiguity to resolve here."""
    if session.title:
        return session.title
    return f"{session.role} at {session.company}"


async def list_sessions_for_docs_page(db: AsyncSession, user_id: str) -> list[CoverLetterSessionSummary]:
    """Powers the "My Docs" page - every saved cover letter, most recent
    first. No preview_html (plain text, no template rendering) and no
    opportunity/application batch-fetch (display label never depends on
    them), unlike resume_tailor's equivalent."""
    sessions = await CoverLetterSessionRepository(db).list(user_id, order_by=CoverLetterSession.created_at.desc())
    return [
        CoverLetterSessionSummary(
            id=str(s.id),
            title=s.title,
            display_label=_session_display_label(s),
            created_at=s.created_at.isoformat(),
            source_opportunity_id=str(s.source_opportunity_id) if s.source_opportunity_id else None,
            source_application_id=str(s.source_application_id) if s.source_application_id else None,
        )
        for s in sessions
    ]
