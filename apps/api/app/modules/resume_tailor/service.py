"""DB touchpoints for resume-tailor: profile overlay reads + resume-artifact
logging, plus render_cv_template_html (rendering.render_html wrapped with the
lebenslauf profile-photo overlay, which needs a DB read + Redis cache). Pure
rendering (Jinja/WeasyPrint, no DB) still lives in rendering.py - this file
only owns the DB-touching orchestration around it, shared by routes.py's
/preview, /preview/thumbnails, and this module's own My Docs card previews.
"""

import json

import cloudinary.utils
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cache import get_cached, set_cached
from app.shared.utils import row_to_dict
from app.shared import cloudinary_client  # noqa: F401 — import triggers cloudinary.config() setup
from app.modules.profile.models import Profile
from app.modules.job_search.models import JobSearchApplication
from app.modules.resume_tailor import rendering
from app.modules.resume_tailor.models import SavedResume, TailoringSession
from app.modules.resume_tailor.repository import TailoringSessionRepository
from app.modules.resume_tailor.schemas import SessionSummary
from app.modules.startup_hunt.models import OpportunityArtifact, StartupHuntOpportunity


def _stringify_date(d):
    """profiles.date_of_birth is a SQL Date; supabase-py used to hand back an
    ISO string (from PostgREST JSON), and callers (json.dumps for the
    lebenslauf cache, Jinja template rendering) expect that same string wire
    format — not a Python date object."""
    return d.isoformat() if d is not None else None


async def get_profile_for_overlay(db: AsyncSession, user_id: str) -> dict:
    """Full profile row, used to overlay contact fields onto AI-structured cv_data."""
    row = (await db.execute(select(Profile).where(Profile.id == user_id))).scalar_one_or_none()
    if row is None:
        return {}
    d = row_to_dict(row)
    d["date_of_birth"] = _stringify_date(d.get("date_of_birth"))
    return d


async def get_profile_photo_fields(db: AsyncSession, user_id: str) -> dict:
    """cv_photo_url/date_of_birth/nationality only — the lebenslauf template's needs."""
    row = (await db.execute(select(Profile).where(Profile.id == user_id))).scalar_one_or_none()
    if row is None:
        return {}
    return {
        "cv_photo_url": row.cv_photo_url,
        "date_of_birth": _stringify_date(row.date_of_birth),
        "nationality": row.nationality,
    }


async def render_cv_template_html(db: AsyncSession, user_id: str, template_id: str, cv_data: dict) -> str:
    """Renders one template against cv_data - moved here (not routes.py) so
    it can be called both from routes.py (/preview, /preview/thumbnails) and
    from this module's own list_sessions_for_docs_page without a circular
    import (routes.py already imports this module to include its routers).

    Callers must already have run rendering.normalize_cv_data on cv_data -
    that step is template-independent, so a batch caller (e.g.
    /preview/thumbnails) runs it once rather than once per template.
    """
    data = dict(cv_data)
    if template_id == "lebenslauf":
        lebenslauf_cache_key = f"lebenslauf_profile:{user_id}"
        cached_profile = await get_cached(lebenslauf_cache_key)
        if cached_profile:
            lp = json.loads(cached_profile)
        else:
            profile = await get_profile_photo_fields(db, user_id)
            lp = await rendering.fetch_lebenslauf_photo_fields(profile)
            await set_cached(lebenslauf_cache_key, json.dumps(lp), ttl_seconds=3600)
        data.update(lp)
    else:
        data.setdefault("photo_base64", None)
        data.setdefault("date_of_birth", None)
        data.setdefault("nationality", None)
    return rendering.render_html(template_id, data)


async def verify_opportunity_ownership(db: AsyncSession, user_id: str, opportunity_id: str) -> bool:
    """True if opportunity_id exists and belongs to user_id. Used to validate
    the optional source_opportunity_id linkage on a new tailoring session —
    never trust a client-supplied id without re-checking ownership."""
    row = (
        await db.execute(
            select(StartupHuntOpportunity.id).where(
                StartupHuntOpportunity.id == opportunity_id, StartupHuntOpportunity.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def verify_application_ownership(db: AsyncSession, user_id: str, application_id: str) -> bool:
    """True if application_id exists and belongs to user_id. Used to validate
    the optional source_application_id linkage on a new tailoring session."""
    row = (
        await db.execute(
            select(JobSearchApplication.id).where(
                JobSearchApplication.id == application_id, JobSearchApplication.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def fetch_saved_resume_bytes(saved_resume: SavedResume) -> bytes:
    """Fetches a saved resume's PDF bytes from Cloudinary. Derives a fresh
    signed URL from the stored public_id on every call rather than persisting
    one — signed URLs expire, and re-deriving one is a local, no-network-call
    computation (uses the already-configured API secret), so there's nothing
    to cache. No SSRF guard needed here (unlike rendering.py::safe_photo_url)
    — the URL is always built server-side from our own trusted
    cloudinary_public_id, never a client-supplied string."""
    url, _ = cloudinary.utils.cloudinary_url(
        saved_resume.cloudinary_public_id, resource_type="raw", type="authenticated", sign_url=True,
    )
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


def _session_display_label(
    session: TailoringSession,
    opportunities: dict[str, StartupHuntOpportunity],
    applications: dict[str, JobSearchApplication],
) -> tuple[str, bool]:
    """Fallback chain for "My Docs": user-set title, then a real linked
    job (factual, DB-backed), then an AI-parsed one (model output, could
    mismatch a multi-company JD), then a generic label. Returns
    (display_label, is_ai_matched) - the frontend only flags the AI-parsed
    case as a best-guess, since the first two are trustworthy as-is."""
    if session.title:
        return session.title, False

    if session.source_opportunity_id:
        opp = opportunities.get(str(session.source_opportunity_id))
        if opp is not None:
            return f"{opp.role_title} at {opp.company_name}", False
    if session.source_application_id:
        app = applications.get(str(session.source_application_id))
        if app is not None:
            return f"{app.role} at {app.company}", False

    prose = session.prose or {}
    target_role = (prose.get("target_role") or "").strip()
    target_company = (prose.get("target_company") or "").strip()
    if target_role and target_company:
        return f"{target_role} at {target_company}", True

    return "Standalone Resume", False


async def list_sessions_for_docs_page(db: AsyncSession, user_id: str) -> list[SessionSummary]:
    """Powers the "My Docs" page - every generated resume, most recent
    first, labeled with the real job it was tailored for when we can tell
    (see _session_display_label). No SQLAlchemy relationships exist between
    TailoringSession and StartupHuntOpportunity/JobSearchApplication, so this
    batches the two lookups (at most one query each) instead of querying per
    session - the two IN-list SELECTs stay tiny even with many sessions."""
    sessions = await TailoringSessionRepository(db).list(user_id, order_by=TailoringSession.created_at.desc())

    opportunity_ids = {str(s.source_opportunity_id) for s in sessions if s.source_opportunity_id}
    application_ids = {str(s.source_application_id) for s in sessions if s.source_application_id}

    opportunities: dict[str, StartupHuntOpportunity] = {}
    if opportunity_ids:
        rows = (
            await db.execute(select(StartupHuntOpportunity).where(StartupHuntOpportunity.id.in_(opportunity_ids)))
        ).scalars()
        opportunities = {str(o.id): o for o in rows}

    applications: dict[str, JobSearchApplication] = {}
    if application_ids:
        rows = (
            await db.execute(select(JobSearchApplication).where(JobSearchApplication.id.in_(application_ids)))
        ).scalars()
        applications = {str(a.id): a for a in rows}

    summaries = []
    for s in sessions:
        display_label, is_ai_matched = _session_display_label(s, opportunities, applications)
        preview_html = None
        if s.draft_cv_data is not None:
            # Only for sessions that already have a draft - draft_cv_data is
            # a snapshot of whatever the editor last held (already normalized
            # and, for lebenslauf, already carrying photo_base64 from when it
            # was first computed), so this is a cheap Jinja-only render, no
            # AI and no fresh Cloudinary fetch. A session with no draft yet
            # would otherwise need the SAME work opening the editor does for
            # the first time (including a structuring LLM call for a
            # never-before-seen resume) just to show a thumbnail on a list
            # page - not worth that cost, so it gets no preview instead.
            cv_data = dict(s.draft_cv_data)
            rendering.normalize_cv_data(cv_data)
            preview_html = await render_cv_template_html(db, user_id, s.template_id or "standard", cv_data)
        summaries.append(SessionSummary(
            id=str(s.id),
            title=s.title,
            display_label=display_label,
            is_ai_matched=is_ai_matched,
            template_id=s.template_id,
            match_score=(s.analysis or {}).get("match_score", 0),
            created_at=s.created_at.isoformat(),
            is_draft=s.draft_cv_data is not None,
            preview_html=preview_html,
        ))
    return summaries


async def save_resume_artifact(
    db: AsyncSession, user_id: str, opportunity_id: str, template_id: str, match_score
) -> None:
    """Best-effort log of a generated PDF against a Startup Hunt opportunity.
    Silently no-ops on failure, matching the original try/except pass."""
    try:
        db.add(
            OpportunityArtifact(
                user_id=user_id,
                opportunity_id=opportunity_id,
                artifact_type="resume_analysis",
                tool_used="resume-tailor",
                content=f"[Generated PDF — template: {template_id}]",
                metadata_={"template_id": template_id, "match_score": match_score},
            )
        )
        await db.flush()
    except Exception:
        pass
