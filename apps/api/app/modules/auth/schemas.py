"""Clerk webhook payload shape. Clerk's `data` object varies by event type
and is large (full user resource) — modeled loosely rather than field-by-field
to avoid brittleness; routes.py extracts only what it needs from it."""

from typing import Any
from pydantic import BaseModel


class ClerkWebhookEvent(BaseModel):
    type: str
    data: dict[str, Any]
