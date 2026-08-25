"""ARQ task that processes the bulk email queue.

Personalises the template, checks the Resend-side rate limiter, calls
Resend, and updates recipient status. Runs as a plain async function, using
the same async SQLAlchemy session pattern as the rest of the FastAPI app.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from arq import Retry
from sqlalchemy import select, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.bulk_email.models import EmailCampaign, EmailRecipient
from app.services.email import send_email
from app.workers.rate_limiter import acquire_token

logger = logging.getLogger(__name__)

RESEND_BUCKET_KEY = "bulk_email:resend_bucket"


def _fill_template(template: str, variables: dict) -> str:
    """Replace {{placeholder}} with values from the variables dict."""
    def replace(match):
        key = match.group(1).strip()
        return variables.get(key, match.group(0))
    return re.sub(r"\{\{([^}]+)\}\}", replace, template)


async def send_campaign_email(
    ctx: dict,
    campaign_id: str,
    recipient_id: str,
    to_email: str,
    to_name: str,
    subject: str,
    body_template: str,
    variables: dict,
):
    """Send one email in a bulk campaign.

    Retries via arq's Retry mechanism (see WorkerSettings.max_tries) on
    transient failures and when the Resend rate limiter has no tokens left.
    """
    if not await acquire_token(ctx["redis"], RESEND_BUCKET_KEY, settings.bulk_email_sends_per_second):
        raise Retry(defer=1)

    async with AsyncSessionLocal() as session:
        # Atomic claim: only proceed if this recipient hasn't already been
        # picked up by a prior attempt (e.g. a retry after a mid-send crash).
        claimed = await session.execute(
            update(EmailRecipient)
            .where(EmailRecipient.id == recipient_id, EmailRecipient.status == "queued")
            .values(status="sending")
        )
        await session.commit()
        if claimed.rowcount == 0:
            return

        try:
            all_vars = {"name": to_name, "email": to_email, **variables}
            personalised_subject = _fill_template(subject, all_vars)
            personalised_body = _fill_template(body_template, all_vars)

            await send_email(
                to_email=to_email,
                to_name=to_name,
                subject=personalised_subject,
                body=personalised_body,
                campaign_id=campaign_id,
            )

            recipient = await session.get(EmailRecipient, recipient_id)
            recipient.status = "sent"
            recipient.sent_at = datetime.now(timezone.utc)
            await session.commit()

        except Exception as exc:
            await session.rollback()
            if ctx["job_try"] < ctx["max_tries"]:
                # Reset to queued so the retry's claim above succeeds.
                await session.execute(
                    update(EmailRecipient)
                    .where(EmailRecipient.id == recipient_id)
                    .values(status="queued")
                )
                await session.commit()
                raise Retry(defer=60) from exc

            await session.execute(
                update(EmailRecipient)
                .where(EmailRecipient.id == recipient_id)
                .values(status="failed", error=str(exc)[:500])
            )
            await session.commit()


async def sweep_stuck_email_sends(ctx: dict) -> None:
    """Catches recipients left at status='sending' by a send_campaign_email
    that never reached its own except block - the worker process was
    killed/crashed between the atomic claim (status='sending', committed)
    and the try/except around the actual send, the one window that block's
    own Retry-based recovery can't cover. ARQ itself won't retry this either
    (a plain, uncaught process death isn't a job-level exception it sees at
    all). Same class of gap as startup_hunt's stuck-'resolving' sweep - see
    modules/startup_hunt/ingestion/scheduler.py's docstring for the fuller
    explanation of why ARQ's max_tries doesn't cover this on its own.

    No attempt cap here (contrast with the startup_hunt sweep, which caps via
    consecutive_failures) - this window only opens on an actual process kill,
    never on a normal application-level failure (those are all caught inside
    the try/except above and go through send_campaign_email's own bounded
    Retry/max_tries path), so there's no realistic way for this sweep to keep
    re-grabbing the same recipient forever the way a data-related crash in
    resolution could.
    """
    stuck_cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=settings.bulk_email_stuck_sending_after_minutes
    )
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(EmailRecipient, EmailCampaign)
                .join(EmailCampaign, EmailCampaign.id == EmailRecipient.campaign_id)
                .where(
                    EmailRecipient.status == "sending",
                    EmailRecipient.updated_at < stuck_cutoff,
                    EmailCampaign.status == "sending",
                )
                .limit(settings.bulk_email_sweep_batch_size)
            )
        ).all()
        if not rows:
            return

        stuck_ids = [recipient.id for recipient, _ in rows]
        await session.execute(
            update(EmailRecipient).where(EmailRecipient.id.in_(stuck_ids)).values(status="queued")
        )
        await session.commit()

        # Captured while the session (and thus the joined EmailCampaign rows)
        # is still open - re-enqueue happens after the session closes below.
        jobs = [
            dict(
                campaign_id=str(campaign.id),
                recipient_id=str(recipient.id),
                to_email=recipient.email,
                to_name=recipient.name,
                subject=campaign.subject,
                body_template=campaign.body,
                variables=recipient.variables,
            )
            for recipient, campaign in rows
        ]

    for job in jobs:
        await ctx["redis"].enqueue_job("send_campaign_email", **job)
    logger.info("Re-enqueued %d stuck email send(s)", len(jobs))
