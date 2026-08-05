"""Bulk email campaign business logic — SQLAlchemy-backed.

email_recipients has no user_id column (ownership is derived transitively
through campaign_id), so it doesn't use UserScopedRepository directly —
every recipient query is scoped by first verifying campaign ownership.
"""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.shared.repository import UserScopedRepository
from app.shared.utils import row_to_dict
from app.modules.bulk_email.models import EmailCampaign, EmailRecipient
from app.modules.bulk_email.schemas import CreateCampaignRequest
from app.modules.bulk_email.tasks import send_campaign_email


class CampaignRepository(UserScopedRepository[EmailCampaign]):
    model = EmailCampaign


async def _get_owned_campaign(db: AsyncSession, user_id: str, campaign_id: str) -> EmailCampaign:
    campaign = await CampaignRepository(db).get(user_id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


async def list_campaigns(db: AsyncSession, user_id: str) -> list[dict]:
    rows = await CampaignRepository(db).list(user_id, order_by=EmailCampaign.created_at.desc())
    return [row_to_dict(r) for r in rows]


async def list_recipients(db: AsyncSession, user_id: str, campaign_id: str) -> list[dict]:
    await _get_owned_campaign(db, user_id, campaign_id)
    rows = (
        await db.execute(
            select(EmailRecipient)
            .where(EmailRecipient.campaign_id == campaign_id)
            .order_by(EmailRecipient.id)
        )
    ).scalars().all()
    return [row_to_dict(r) for r in rows]


async def create_campaign(db: AsyncSession, user_id: str, body: CreateCampaignRequest) -> dict:
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    campaign_ids_this_month = select(EmailCampaign.id).where(
        EmailCampaign.user_id == user_id, EmailCampaign.created_at >= month_start
    )
    monthly_sent = await db.scalar(
        select(func.count())
        .select_from(EmailRecipient)
        .where(
            EmailRecipient.campaign_id.in_(campaign_ids_this_month),
            EmailRecipient.status == "sent",
        )
    ) or 0

    if monthly_sent + len(body.recipients) > settings.rate_limit_bulk_email_per_month:
        remaining = max(0, settings.rate_limit_bulk_email_per_month - monthly_sent)
        raise HTTPException(
            status_code=429,
            detail=(
                f"Monthly email limit of {settings.rate_limit_bulk_email_per_month} would be "
                f"exceeded. You have {remaining} remaining this month."
            ),
        )

    campaign = await CampaignRepository(db).create(
        user_id,
        name=body.name,
        subject=body.subject,
        body=body.body,
        status="queued",
        delay_seconds=body.delay_seconds,
    )

    recipients = [
        EmailRecipient(
            campaign_id=campaign.id,
            email=r.email,
            name=r.name,
            variables=r.variables,
            status="queued",
        )
        for r in body.recipients
    ]
    db.add_all(recipients)
    await db.flush()
    for r in recipients:
        await db.refresh(r)

    for i, recipient in enumerate(recipients):
        delay_seconds = i * body.delay_seconds
        send_campaign_email.apply_async(
            kwargs={
                "campaign_id": str(campaign.id),
                "recipient_id": str(recipient.id),
                "to_email": recipient.email,
                "to_name": recipient.name,
                "subject": body.subject,
                "body_template": body.body,
                "variables": recipient.variables,
            },
            countdown=delay_seconds,
        )

    campaign.status = "sending"
    await db.flush()
    await db.refresh(campaign)

    return {**row_to_dict(campaign), "recipient_count": len(recipients)}


async def get_campaign_status(db: AsyncSession, user_id: str, campaign_id: str) -> dict:
    campaign = await _get_owned_campaign(db, user_id, campaign_id)

    recipient_rows = (
        await db.execute(
            select(EmailRecipient).where(EmailRecipient.campaign_id == campaign_id)
        )
    ).scalars().all()
    recipients = [row_to_dict(r) for r in recipient_rows]

    sent = sum(1 for r in recipients if r["status"] == "sent")
    failed = sum(1 for r in recipients if r["status"] == "failed")
    total = len(recipients)

    if total > 0 and (sent + failed) == total and campaign.status == "sending":
        campaign.status = "completed" if failed == 0 else "failed"
        await db.flush()
        await db.refresh(campaign)

    return {
        **row_to_dict(campaign),
        "recipients": recipients,
        "stats": {"sent": sent, "failed": failed, "total": total, "queued": total - sent - failed},
    }


async def pause_campaign(db: AsyncSession, user_id: str, campaign_id: str) -> None:
    campaign = await _get_owned_campaign(db, user_id, campaign_id)
    campaign.status = "paused"
    await db.flush()
    # Note: Celery tasks already queued will still run unless manually revoked.
    # For a production pause, use Celery's revoke() with a task ID list.
