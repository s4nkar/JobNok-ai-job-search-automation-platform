"""Bulk email campaign management router.

Creates campaigns, enqueues recipients to Celery, and provides live status.
"""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException

from app.core.config import settings
from app.core.security import get_user_id
from app.integrations.supabase_client import get_supabase
from app.services.cache import check_rate_limit
from app.modules.bulk_email.schemas import CreateCampaignRequest
from app.modules.bulk_email.tasks import send_campaign_email

router = APIRouter()


@router.post("/campaign")
async def create_campaign(request: Request, body: CreateCampaignRequest):
    user_id = get_user_id(request)
    supabase = get_supabase()
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    campaigns_this_month = await asyncio.to_thread(
        lambda: supabase.from_("email_campaigns")
        .select("id")
        .eq("user_id", user_id)
        .gte("created_at", month_start)
        .execute()
    )

    if campaigns_this_month.data:
        campaign_ids = [c["id"] for c in campaigns_this_month.data]
        sent_count = await asyncio.to_thread(
            lambda: supabase.from_("email_recipients")
            .select("id", count="exact")
            .in_("campaign_id", campaign_ids)
            .eq("status", "sent")
            .execute()
        )
        monthly_sent = sent_count.count or 0
    else:
        monthly_sent = 0

    if monthly_sent + len(body.recipients) > settings.rate_limit_bulk_email_per_month:
        remaining = max(0, settings.rate_limit_bulk_email_per_month - monthly_sent)
        raise HTTPException(
            status_code=429,
            detail=f"Monthly email limit of {settings.rate_limit_bulk_email_per_month} would be exceeded. You have {remaining} remaining this month."
        )

    campaign_res = await asyncio.to_thread(
        lambda: supabase.from_("email_campaigns").insert({
            "user_id": user_id,
            "name": body.name,
            "subject": body.subject,
            "body": body.body,
            "status": "queued",
            "delay_seconds": body.delay_seconds,
        }).select().single().execute()
    )

    if not campaign_res.data:
        raise HTTPException(status_code=500, detail="Failed to create campaign")

    campaign = campaign_res.data
    campaign_id = campaign["id"]

    recipients_data = [
        {
            "campaign_id": campaign_id,
            "email": r.email,
            "name": r.name,
            "variables": r.variables,
            "status": "queued",
        }
        for r in body.recipients
    ]
    recipients_res = await asyncio.to_thread(
        lambda: supabase.from_("email_recipients").insert(recipients_data).execute()
    )
    recipients = recipients_res.data or []

    for i, recipient in enumerate(recipients):
        delay_seconds = i * body.delay_seconds
        send_campaign_email.apply_async(
            kwargs={
                "campaign_id": campaign_id,
                "recipient_id": recipient["id"],
                "to_email": recipient["email"],
                "to_name": recipient["name"],
                "subject": body.subject,
                "body_template": body.body,
                "variables": recipient["variables"],
            },
            countdown=delay_seconds,
        )

    await asyncio.to_thread(
        lambda: supabase.from_("email_campaigns").update({"status": "sending"}).eq("id", campaign_id).execute()
    )

    return {**campaign, "status": "sending", "recipient_count": len(recipients)}


@router.get("/campaign/{campaign_id}/status")
async def get_campaign_status(request: Request, campaign_id: str):
    user_id = get_user_id(request)
    supabase = get_supabase()

    campaign_res = await asyncio.to_thread(
        lambda: supabase.from_("email_campaigns")
        .select("*")
        .eq("id", campaign_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not campaign_res.data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    recipients_res = await asyncio.to_thread(
        lambda: supabase.from_("email_recipients")
        .select("*")
        .eq("campaign_id", campaign_id)
        .execute()
    )

    recipients = recipients_res.data or []
    sent = sum(1 for r in recipients if r["status"] == "sent")
    failed = sum(1 for r in recipients if r["status"] == "failed")
    total = len(recipients)

    campaign = campaign_res.data
    if total > 0 and (sent + failed) == total and campaign["status"] == "sending":
        status = "completed" if failed == 0 else "failed"
        await asyncio.to_thread(
            lambda: supabase.from_("email_campaigns").update({"status": status}).eq("id", campaign_id).execute()
        )
        campaign["status"] = status

    return {
        **campaign,
        "recipients": recipients,
        "stats": {"sent": sent, "failed": failed, "total": total, "queued": total - sent - failed},
    }


@router.post("/campaign/{campaign_id}/pause")
async def pause_campaign(request: Request, campaign_id: str):
    user_id = get_user_id(request)
    supabase = get_supabase()

    result = await asyncio.to_thread(
        lambda: supabase.from_("email_campaigns")
        .update({"status": "paused"})
        .eq("id", campaign_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Note: Celery tasks already queued will still run unless manually revoked.
    # For a production pause, use Celery's revoke() with a task ID list.
    return {"status": "paused"}
