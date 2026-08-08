"""User profile CRUD — personal details + CV photo used by resume templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.modules.profile import service

router = APIRouter()


@router.get("")
async def get_profile(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    return await service.get_profile(db, user_id)


@router.put("")
async def update_profile(request: Request, body: dict, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    return await service.update_profile(db, user_id, body)


@router.post("/photo")
async def upload_cv_photo(
    request: Request, photo: UploadFile = File(...), db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    if photo.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=422, detail="Only JPEG, PNG, or WebP images accepted")

    data = await photo.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be under 5 MB")

    public_url = await service.upload_cv_photo(user_id, data)
    await service.update_cv_photo_url(db, user_id, public_url)
    return {"cv_photo_url": public_url}
