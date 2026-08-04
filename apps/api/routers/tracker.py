"""Job application tracker CRUD endpoints."""

import asyncio
import datetime
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, field_validator
from typing import Optional

from lib.supabase_client import get_supabase, get_user_id

router = APIRouter()


class ApplicationIn(BaseModel):
    company: str
    role: str
    applied_at: str
    status: str
    follow_up_date: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    notes: Optional[str] = None

    @field_validator("applied_at")
    @classmethod
    def validate_applied_at(cls, v: str) -> str:
        try:
            datetime.date.fromisoformat(v)
        except ValueError:
            raise ValueError("applied_at must be ISO 8601 date (YYYY-MM-DD)")
        return v

    @field_validator("follow_up_date")
    @classmethod
    def validate_follow_up_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                datetime.date.fromisoformat(v)
            except ValueError:
                raise ValueError("follow_up_date must be ISO 8601 date (YYYY-MM-DD)")
        return v


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
