"""Celery task that processes the bulk email queue.

Picks up email jobs from the Redis queue, personalises templates, calls
Resend, and updates recipient status in Supabase.
"""

import re
from app.workers.celery_app import celery_app
from app.services.email import send_email
from app.integrations.supabase_client import get_supabase


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
    supabase = get_supabase()

    # Mark as sending
    supabase.from_("email_recipients") \
        .update({"status": "sending"}) \
        .eq("id", recipient_id) \
        .execute()

    try:
        # Personalise template with recipient variables
        all_vars = {"name": to_name, "email": to_email, **variables}
        personalised_subject = _fill_template(subject, all_vars)
        personalised_body = _fill_template(body_template, all_vars)

        import asyncio
        asyncio.run(
            send_email(
                to_email=to_email,
                to_name=to_name,
                subject=personalised_subject,
                body=personalised_body,
                campaign_id=campaign_id,
            )
        )

        # Mark as sent
        from datetime import datetime, timezone
        supabase.from_("email_recipients") \
            .update({"status": "sent", "sent_at": datetime.now(timezone.utc).isoformat()}) \
            .eq("id", recipient_id) \
            .execute()

    except Exception as exc:
        # Retry on transient errors
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            # Final failure — mark as failed
            supabase.from_("email_recipients") \
                .update({"status": "failed", "error": str(exc)[:500]}) \
                .eq("id", recipient_id) \
                .execute()
