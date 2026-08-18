"""ARQ task that processes the bulk email queue.

Personalises the template, checks the Resend-side rate limiter, calls
Resend, and updates recipient status. Runs as a plain async function, using
the same async SQLAlchemy session pattern as the rest of the FastAPI app.
"""

import re
from datetime import datetime, timezone

from arq import Retry
from sqlalchemy import update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.bulk_email.models import EmailRecipient
from app.services.email import send_email
from app.workers.rate_limiter import acquire_token

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
