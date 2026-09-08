"""Shared Cloudinary client — thin async wrappers around the (sync) SDK.

Used by profile/service.py (CV photo) and resume_tailor (saved resumes) so
cloudinary.config(...) is only ever called from one place.
"""

import asyncio

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException

from app.core.config import settings

cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret,
    secure=True,
)


async def upload(data: bytes, *, public_id: str, resource_type: str = "image", **kwargs) -> dict:
    """cloudinary.uploader.upload is sync (blocking network I/O) — offload to
    a thread so it doesn't stall the event loop for other concurrent requests."""
    try:
        return await asyncio.to_thread(
            cloudinary.uploader.upload, data, public_id=public_id, resource_type=resource_type, **kwargs,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {exc}")


async def destroy(public_id: str, *, resource_type: str = "image") -> None:
    """Best-effort — an orphaned Cloudinary asset costs storage, not
    correctness, so a delete failure here must never block the caller's own
    DB-side deletion of the record that referenced it."""
    try:
        await asyncio.to_thread(cloudinary.uploader.destroy, public_id, resource_type=resource_type)
    except Exception:
        pass
