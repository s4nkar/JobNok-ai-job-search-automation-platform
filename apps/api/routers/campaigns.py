"""Email campaign read endpoints (create/status/pause live in email.py)."""

import asyncio
from fastapi import APIRouter, Request, HTTPException

from lib.supabase_client import get_supabase, get_user_id

router = APIRouter()


@router.get("")
async def list_campaigns(request: Request):
    user_id = get_user_id(request)
    sb = get_supabase()
    res = await asyncio.to_thread(
        lambda: sb.table("email_campaigns")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data


@router.get("/{campaign_id}/recipients")
async def list_recipients(request: Request, campaign_id: str):
    user_id = get_user_id(request)
    sb = get_supabase()

    campaign = await asyncio.to_thread(
        lambda: sb.table("email_campaigns")
        .select("id")
        .eq("id", campaign_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not campaign.data:
        raise HTTPException(status_code=404, detail="Not found")

    res = await asyncio.to_thread(
        lambda: sb.table("email_recipients")
        .select("*")
        .eq("campaign_id", campaign_id)
        .order("id")
        .execute()
    )
    return res.data
