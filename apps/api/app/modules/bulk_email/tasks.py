"""Celery task that processes the bulk email queue.

Picks up email jobs from the Redis queue, personalises templates, calls
Resend, and updates recipient status. Uses the SYNC SQLAlchemy session
(app.core.database.SyncSessionLocal) — Celery tasks are plain sync functions
with no event loop, so the async engine/session can't be used here.
"""

import re
import asyncio
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.modules.bulk_email.models import EmailRecipient
from app.services.email import send_email


def _fill_template(template: str, variables: dict) -> str:
    """Replace {{placeholder}} with values from the variables dict."""
    def replace(match):
        key = match.group(1).strip()
        return variables.get(key, match.group(0))
    return re.sub(r"\{\{([^}]+)\}\}", replace, template)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="send_campaign_email",
)
def send_campaign_email(
    self,
    campaign_id: str,
    recipient_id: str,
    to_email: str,
    to_name: str,
    subject: str,
    body_template: str,
    variables: dict,
):
    """Send one email in a bulk campaign.

    Retries up to 3 times on transient failures with 60s backoff.
    """
    with SyncSessionLocal() as session:
        recipient = session.get(EmailRecipient, recipient_id)

        recipient.status = "sending"
        session.commit()

        try:
            # Personalise template with recipient variables
            all_vars = {"name": to_name, "email": to_email, **variables}
            personalised_subject = _fill_template(subject, all_vars)
            personalised_body = _fill_template(body_template, all_vars)

            asyncio.run(
                send_email(
                    to_email=to_email,
                    to_name=to_name,
                    subject=personalised_subject,
                    body=personalised_body,
                    campaign_id=campaign_id,
                )
            )

            recipient.status = "sent"
            recipient.sent_at = datetime.now(timezone.utc)
            session.commit()

        except Exception as exc:
            session.rollback()
            try:
                self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                # Final failure — mark as failed
                recipient.status = "failed"
                recipient.error = str(exc)[:500]
                session.commit()
