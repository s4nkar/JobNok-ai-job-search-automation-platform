"""DB touchpoints for resume-tailor: profile overlay reads + resume-artifact
logging. Everything else in this feature (PDF/HTML rendering, LLM prose,
deterministic matching) is DB-free — see routes.py.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.utils import row_to_dict
from app.modules.profile.models import Profile
from app.modules.job_search.models import JobSearchApplication
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
