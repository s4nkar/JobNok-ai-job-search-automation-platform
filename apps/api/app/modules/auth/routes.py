"""Clerk webhook receiver — the primary path for keeping `profiles` in sync
with Clerk-side identity changes. core/security.py's lookup-or-create is only
a fallback for requests that land before a webhook has processed.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from svix.webhooks import Webhook, WebhookVerificationError

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth import service
from app.modules.auth.schemas import ClerkWebhookEvent

router = APIRouter()


def _extract_identity(data: dict) -> tuple[str, str, str | None]:
    """Pull (clerk_user_id, email, full_name) out of a Clerk user webhook payload."""
    clerk_user_id = data["id"]
    primary_id = data.get("primary_email_address_id")
    email = next(
        (e["email_address"] for e in data.get("email_addresses", []) if e.get("id") == primary_id),
        None,
    ) or f"{clerk_user_id}@unknown.local"
    full_name = " ".join(filter(None, [data.get("first_name"), data.get("last_name")])) or None
    return clerk_user_id, email, full_name


@router.post("/webhook/clerk", status_code=204)
async def clerk_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    try:
        wh = Webhook(settings.clerk_webhook_secret)
        raw_payload = wh.verify(body, dict(request.headers))
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event = ClerkWebhookEvent.model_validate(raw_payload)

    if event.type in ("user.created", "user.updated"):
        clerk_user_id, email, full_name = _extract_identity(event.data)
        await service.upsert_from_webhook(db, clerk_user_id, email, full_name)
    elif event.type == "user.deleted":
        clerk_user_id = event.data.get("id")
        if clerk_user_id:
            await service.delete_by_clerk_id(db, clerk_user_id)
