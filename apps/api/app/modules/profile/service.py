"""Profile CRUD + cross-module profile-existence helper — SQLAlchemy-backed.

profiles.id *is* the user_id (no separate user_id column), so this module
doesn't use UserScopedRepository — every query is scoped by id directly.
"""

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_jwt
from app.modules.profile.models import Profile
from app.shared.utils import row_to_dict

_ALLOWED_FIELDS = {
    "full_name", "job_title", "cv_email", "phone",
    "address_street", "address_city", "address_postal_code", "address_country",
    "date_of_birth", "nationality",
    "linkedin_url", "github_url", "website_url", "work_authorization",
}


def _email_from_request(user_id: str, request: Request) -> str:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    claims = verify_jwt(token)
    return claims.get("email") or f"{user_id}@unknown.local"


async def ensure_profile_exists(db: AsyncSession, user_id: str, request: Request) -> None:
    """Upsert a profiles row so FK constraints don't fail for users whose
    profile trigger missed. Race-safe against a concurrent trigger insert via
    ON CONFLICT DO NOTHING (mirrors the original upsert(on_conflict='id'))."""
    try:
        email = _email_from_request(user_id, request)
        stmt = (
            pg_insert(Profile)
            .values(id=user_id, email=email)
            .on_conflict_do_nothing(index_elements=["id"])
        )
        await db.execute(stmt)
        await db.flush()
    except Exception:
        pass


async def get_or_create_profile(db: AsyncSession, user_id: str, request: Request) -> dict:
    row = (await db.execute(select(Profile).where(Profile.id == user_id))).scalar_one_or_none()
    if row is None:
        # Profile row missing (trigger may have failed at signup) — create a minimal one
        email = _email_from_request(user_id, request)
        stmt = (
            pg_insert(Profile)
            .values(id=user_id, email=email)
            .on_conflict_do_nothing(index_elements=["id"])
        )
        await db.execute(stmt)
        await db.flush()
        row = (await db.execute(select(Profile).where(Profile.id == user_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=500, detail="Could not retrieve or create profile")
    return row_to_dict(row)


async def update_profile(db: AsyncSession, user_id: str, body: dict) -> dict:
    updates = {k: v for k, v in body.items() if k in _ALLOWED_FIELDS}
    if not updates:
        raise HTTPException(status_code=422, detail="No valid fields provided")
    row = (await db.execute(select(Profile).where(Profile.id == user_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    for k, v in updates.items():
        setattr(row, k, v)
    await db.flush()
    await db.refresh(row)
    return row_to_dict(row)


async def update_cv_photo_url(db: AsyncSession, user_id: str, public_url: str) -> None:
    row = (await db.execute(select(Profile).where(Profile.id == user_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    row.cv_photo_url = public_url
    await db.flush()
