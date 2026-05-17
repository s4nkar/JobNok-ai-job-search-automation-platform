"""Email template CRUD endpoints."""

import re
import asyncio
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, field_validator
from typing import Optional

from lib.supabase_client import get_supabase, get_user_id

router = APIRouter()


def extract_placeholders(content: str) -> list[str]:
    matches = re.findall(r"\{\{([^}]+)\}\}", content)
    seen: list[str] = []
    for m in matches:
        key = m.strip()
        if key not in seen:
            seen.append(key)
    return seen


class TemplateIn(BaseModel):
    name: str
    category: str
    content: str

    @field_validator("name")
    @classmethod
    def name_min(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("name must be at least 2 characters")
        return v

    @field_validator("content")
    @classmethod
    def content_min(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("content must be at least 10 characters")
        return v


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None


@router.get("")
async def list_templates(request: Request):
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("templates")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data


@router.post("", status_code=201)
async def create_template(request: Request, body: TemplateIn):
    user_id = get_user_id(request)
    placeholders = extract_placeholders(body.content)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("templates")
        .insert({**body.model_dump(), "user_id": user_id, "placeholders": placeholders})
        .select()
        .single()
        .execute()
    )
    return res.data


@router.put("/{template_id}")
async def update_template(request: Request, template_id: str, body: TemplateUpdate):
    user_id = get_user_id(request)
    # exclude_unset distinguishes "not sent" from "sent as null"
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=422, detail="At least one field must be provided")
    if "content" in payload:
        payload["placeholders"] = extract_placeholders(payload["content"])
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("templates")
        .update(payload)
        .eq("id", template_id)
        .eq("user_id", user_id)
        .select()
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Not found")
    return res.data


@router.delete("/{template_id}", status_code=204)
async def delete_template(request: Request, template_id: str):
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("templates")
        .delete()
        .eq("id", template_id)
        .eq("user_id", user_id)
        .select()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Not found")
