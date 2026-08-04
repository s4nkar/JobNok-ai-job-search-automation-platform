"""Job application tracker CRUD endpoints."""

import asyncio
from fastapi import APIRouter, Request, HTTPException

from app.integrations.supabase_client import get_supabase
from app.core.security import get_user_id
from app.modules.tracker.schemas import ApplicationIn

router = APIRouter()


@router.get("")
async def list_applications(request: Request):
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("job_applications")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data


@router.post("", status_code=201)
async def create_application(request: Request, body: ApplicationIn):
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("job_applications")
        .insert({**body.model_dump(), "user_id": user_id})
        .select()
        .single()
        .execute()
    )
    return res.data


@router.put("/{app_id}")
async def update_application(request: Request, app_id: str, body: ApplicationIn):
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("job_applications")
        .update(body.model_dump())
        .eq("id", app_id)
        .eq("user_id", user_id)
        .select()
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Not found")
    return res.data


@router.delete("/{app_id}", status_code=204)
async def delete_application(request: Request, app_id: str):
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("job_applications")
        .delete()
        .eq("id", app_id)
        .eq("user_id", user_id)
        .select()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Not found")
