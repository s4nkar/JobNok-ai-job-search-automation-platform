"""Saved resumes ("My Resumes") — up to 3 permanent, user-managed resume PDFs.

Included into resume_tailor/routes.py's router (see the bottom of that file),
so everything here still arrives under the same /api/ai prefix main.py
already registers — no changes needed there.

The frontend never receives a Cloudinary URL or public_id — every read of
the actual file (list doesn't need it, but preview/download/compare-with-
original do) goes through GET /resumes/{slot}/file or
GET /tailor/{id}/original-pdf, both of which re-derive a signed URL and
stream bytes back server-side (see service.py::fetch_saved_resume_bytes).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.services.cache import check_burst_limit
from app.modules.resume_tailor import cache as resume_cache
from app.modules.resume_tailor import service as resume_tailor_service
from app.modules.resume_tailor.models import SavedResume
from app.modules.resume_tailor.repository import SavedResumeRepository
from app.modules.resume_tailor.schemas import SavedResumeListResponse, SavedResumeRenameRequest, SavedResumeResponse
from app.shared import cloudinary_client

router = APIRouter()

# Mirrors routes.py's _MAX_PDF_BYTES — kept as its own constant here rather
# than importing a private name across files.
_MAX_PDF_BYTES = 5 * 1024 * 1024  # 5 MB
_VALID_SLOTS = (1, 2, 3)


def _saved_resume_response(row: SavedResume) -> SavedResumeResponse:
    return SavedResumeResponse(
        id=str(row.id),
        slot=row.slot,
        label=row.label,
        original_filename=row.original_filename,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _check_slot(slot: int) -> None:
    if slot not in _VALID_SLOTS:
        raise HTTPException(status_code=422, detail="slot must be 1, 2, or 3")


async def _check_burst(user_id: str, bucket: str) -> None:
    """Same fail-open-on-Redis-error burst guard used throughout routes.py
    (e.g. resume_tailor_draft/title/preview) — none of these endpoints had
    any rate limiting at all before this."""
    try:
        burst_ok = await check_burst_limit(
            user_id, bucket, settings.rate_limit_burst_limit, settings.rate_limit_burst_window_seconds,
        )
    except Exception:
        burst_ok = True
    if not burst_ok:
        raise HTTPException(status_code=429, detail="Too many requests — please wait a few seconds and try again.")


@router.get("/resumes", response_model=SavedResumeListResponse)
async def list_saved_resumes(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    await _check_burst(user_id, "resume_tailor_saved_list")
    rows = await SavedResumeRepository(db).list_ordered(user_id)
    return SavedResumeListResponse(resumes=[_saved_resume_response(r) for r in rows])


@router.put("/resumes/{slot}", response_model=SavedResumeResponse)
async def upload_saved_resume(
    slot: int, request: Request,
    file: UploadFile = File(...), label: str = Form(..., min_length=1, max_length=100),
    db: AsyncSession = Depends(get_db),
):
    _check_slot(slot)
    user_id = await get_current_user_id(request, db)
    await _check_burst(user_id, "resume_tailor_saved_upload")

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="Only PDF files accepted")
    data = await file.read(_MAX_PDF_BYTES + 1)
    if len(data) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF must be ≤ 5 MB")

    repo = SavedResumeRepository(db)
    existing = await repo.get_by_slot(user_id, slot)
    # Fixed, predictable public_id per slot (not Cloudinary's own generated
    # one) — overwrite=True means re-uploading into the same slot replaces
    # the asset in place, so no orphaned Cloudinary asset and no explicit
    # destroy() needed except on outright deletion.
    public_id = f"users/{user_id}/resumes/slot_{slot}"
    result = await cloudinary_client.upload(
        data, public_id=public_id, resource_type="raw", type="authenticated", overwrite=True,
    )
    sha256 = resume_cache.compute_resume_hash(data)
    filename = file.filename or f"resume_{slot}.pdf"

    if existing:
        row = await repo.touch_updated(
            user_id, str(existing.id),
            label=label.strip(), cloudinary_public_id=result["public_id"],
            original_filename=filename, sha256=sha256,
        )
    else:
        row = await repo.create(
            user_id, slot=slot, label=label.strip(), cloudinary_public_id=result["public_id"],
            original_filename=filename, sha256=sha256,
        )
    return _saved_resume_response(row)


@router.patch("/resumes/{slot}", response_model=SavedResumeResponse)
async def rename_saved_resume(slot: int, request: Request, body: SavedResumeRenameRequest, db: AsyncSession = Depends(get_db)):
    _check_slot(slot)
    user_id = await get_current_user_id(request, db)
    await _check_burst(user_id, "resume_tailor_saved_rename")

    repo = SavedResumeRepository(db)
    existing = await repo.get_by_slot(user_id, slot)
    if existing is None:
        raise HTTPException(status_code=404, detail="No resume in this slot")

    row = await repo.touch_updated(user_id, str(existing.id), label=body.label.strip())
    return _saved_resume_response(row)


@router.delete("/resumes/{slot}")
async def delete_saved_resume(slot: int, request: Request, db: AsyncSession = Depends(get_db)):
    _check_slot(slot)
    user_id = await get_current_user_id(request, db)
    await _check_burst(user_id, "resume_tailor_saved_delete")

    repo = SavedResumeRepository(db)
    existing = await repo.get_by_slot(user_id, slot)
    if existing is None:
        raise HTTPException(status_code=404, detail="No resume in this slot")

    await cloudinary_client.destroy(existing.cloudinary_public_id, resource_type="raw")
    await repo.delete(user_id, str(existing.id))
    return {"deleted": True}


@router.get("/resumes/{slot}/file")
async def get_saved_resume_file(slot: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Streams the PDF for a slot — used by the profile page's preview/
    download action. Same authenticated-proxy shape as
    GET /tailor/{id}/original-pdf, just addressed by slot instead of session."""
    _check_slot(slot)
    user_id = await get_current_user_id(request, db)
    await _check_burst(user_id, "resume_tailor_saved_file")

    saved_resume = await SavedResumeRepository(db).get_by_slot(user_id, slot)
    if saved_resume is None:
        raise HTTPException(status_code=404, detail="No resume in this slot")

    pdf_bytes = await resume_tailor_service.fetch_saved_resume_bytes(saved_resume)
    return Response(content=pdf_bytes, media_type="application/pdf")
