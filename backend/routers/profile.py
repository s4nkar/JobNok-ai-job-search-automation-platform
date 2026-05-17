"""User profile CRUD — personal details + CV photo used by resume templates."""

from __future__ import annotations

import asyncio
import httpx
from fastapi import APIRouter, HTTPException, Request, UploadFile, File

from lib.config import settings
from lib.supabase_client import get_supabase, get_user_id

router = APIRouter()

_ALLOWED_FIELDS = {
    "full_name", "job_title", "cv_email", "phone",
    "address_street", "address_city", "address_postal_code", "address_country",
    "date_of_birth", "nationality",
    "linkedin_url", "github_url", "website_url", "work_authorization",
}

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
async def get_profile(request: Request):
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("profiles").select("*").eq("id", user_id).limit(1).execute()
    )
    row = (res.data or [None])[0]
    if not row:
        # Profile row missing (trigger may have failed at signup) — create a minimal one
        from lib.supabase_client import verify_jwt
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        claims = verify_jwt(token)
        email = claims.get("email") or f"{user_id}@unknown.local"
        ins = await asyncio.to_thread(
            lambda: sb.table("profiles")
            .upsert({"id": user_id, "email": email}, on_conflict="id")
            .select()
            .execute()
        )
        row = (ins.data or [None])[0]
    if not row:
        raise HTTPException(status_code=500, detail="Could not retrieve or create profile")
    return row


@router.put("")
async def update_profile(request: Request, body: dict):
    user_id = get_user_id(request)
    updates = {k: v for k, v in body.items() if k in _ALLOWED_FIELDS}
    if not updates:
        raise HTTPException(status_code=422, detail="No valid fields provided")
    sb = get_supabase()
    await asyncio.to_thread(
        lambda: sb.table("profiles").update(updates).eq("id", user_id).execute()
    )
    res = await asyncio.to_thread(
        lambda: sb.table("profiles").select("*").eq("id", user_id).single().execute()
    )
    return res.data


@router.post("/photo")
async def upload_cv_photo(request: Request, photo: UploadFile = File(...)):
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

    sb = get_supabase()
    await asyncio.to_thread(
        lambda: sb.table("profiles")
        .update({"cv_photo_url": public_url})
        .eq("id", user_id)
        .execute()
    )
    return {"cv_photo_url": public_url}
