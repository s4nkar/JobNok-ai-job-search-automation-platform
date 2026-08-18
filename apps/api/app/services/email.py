"""Resend email sender.

Handles single sends for the bulk email ARQ worker.
Auto-injects an unsubscribe footer on all campaign emails.
"""

import resend
from app.core.config import settings

resend.api_key = settings.resend_api_key

UNSUBSCRIBE_FOOTER = """

---
You're receiving this email because someone used JobNok to contact you.
To unsubscribe from future emails from this sender, reply with "Unsubscribe".
"""


async def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    campaign_id: str | None = None,
) -> dict:
    """Send a single email via Resend.

    Returns the Resend API response dict.
    Raises on API error.
    """
    full_body = body + UNSUBSCRIBE_FOOTER

    params: resend.Emails.SendParams = {
        "from": f"{settings.resend_from_name} <{settings.resend_from_email}>",
        "to": [f"{to_name} <{to_email}>"],
        "subject": subject,
        "text": full_body,
        "headers": {
            "List-Unsubscribe": f"<mailto:{settings.resend_from_email}?subject=Unsubscribe>",
        },
        "tags": [{"name": "campaign_id", "value": campaign_id or "direct"}],
    }

    response = resend.Emails.send(params)
    return response
