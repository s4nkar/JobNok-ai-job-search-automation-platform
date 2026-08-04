"""User profile CRUD — personal details + CV photo used by resume templates."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_user_id
from app.modules.profile import service

router = APIRouter()

_STORAGE_HEADERS = lambda: {
    "Authorization": f"Bearer {settings.supabase_service_role_key}",
    "apikey": settings.supabase_service_role_key,
}


async def _ensure_cv_photos_bucket(client: httpx.AsyncClient) -> None:
    """Create cv-photos bucket if it doesn't exist — idempotent."""
    await client.post(
        f"{settings.supabase_url}/storage/v1/bucket",
        headers={**_STORAGE_HEADERS(), "Content-Type": "application/json"},
        json={"id": "cv-photos", "name": "cv-photos", "public": True},
    )
    # 200 = created, 409 = already exists — both are fine, ignore other errors


@router.get("")
async def get_profile(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    return await service.get_or_create_profile(db, user_id, request)


@router.put("")
async def update_profile(request: Request, body: dict, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    return await service.update_profile(db, user_id, body)


@router.post("/photo")
async def upload_cv_photo(
    request: Request, photo: UploadFile = File(...), db: AsyncSession = Depends(get_db)
):
    user_id = get_user_id(request)
    if photo.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=422, detail="Only JPEG, PNG, or WebP images accepted")

    data = await photo.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be under 5 MB")

    ext = "jpg" if photo.content_type == "image/jpeg" else photo.content_type.split("/")[1]
    path = f"{user_id}/cv_photo.{ext}"
    object_url = f"{settings.supabase_url}/storage/v1/object/cv-photos/{path}"

    async with httpx.AsyncClient(timeout=30) as client:
        # Ensure bucket exists (creates it if missing)
        await _ensure_cv_photos_bucket(client)

        # Upload file
        res = await client.post(
            object_url,
            headers={
                **_STORAGE_HEADERS(),
                "Content-Type": photo.content_type,
                "x-upsert": "true",
            },
            content=data,
        )
        if res.status_code not in (200, 201):
            raise HTTPException(
                status_code=500,
                detail=f"Storage upload failed ({res.status_code}): {res.text}",
            )

    public_url = f"{settings.supabase_url}/storage/v1/object/public/cv-photos/{path}"
    await service.update_cv_photo_url(db, user_id, public_url)
    return {"cv_photo_url": public_url}
