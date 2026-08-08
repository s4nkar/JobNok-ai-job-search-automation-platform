"""Profile CRUD — SQLAlchemy-backed.

profiles.id *is* the user_id (no separate user_id column), so this module
doesn't use UserScopedRepository — every query is scoped by id directly.
Profile existence is guaranteed by the time any route here runs (see
core/security.py::get_current_user_id + app/modules/auth/service.py), so no
upsert-on-read fallback is needed — a missing row here would be a genuine bug.
"""

import asyncio

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.profile.models import Profile
from app.shared.utils import row_to_dict

cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret,
    secure=True,
)

_ALLOWED_FIELDS = {
    "full_name", "job_title", "cv_email", "phone",
    "address_street", "address_city", "address_postal_code", "address_country",
    "date_of_birth", "nationality",
    "linkedin_url", "github_url", "website_url", "work_authorization",
}


async def get_profile(db: AsyncSession, user_id: str) -> dict:
    row = (await db.execute(select(Profile).where(Profile.id == user_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Profile not found")
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


async def upload_cv_photo(user_id: str, data: bytes) -> str:
    """Upload a CV photo to Cloudinary and return its public URL.

    cloudinary's SDK is sync (blocking network I/O) — offload to a thread so
    it doesn't stall the event loop for other concurrent requests.
    """
    try:
        result = await asyncio.to_thread(
            cloudinary.uploader.upload,
            data,
            public_id=f"users/{user_id}/avatar",
            overwrite=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {exc}")
    return result["secure_url"]


async def update_cv_photo_url(db: AsyncSession, user_id: str, public_url: str) -> None:
    row = (await db.execute(select(Profile).where(Profile.id == user_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    row.cv_photo_url = public_url
    await db.flush()
