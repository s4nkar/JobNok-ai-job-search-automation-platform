"""Request/response models for the bulk-email feature."""

from typing import Any
from pydantic import BaseModel, field_validator
from app.core.config import settings


class RecipientInput(BaseModel):
    email: str
    name: str
    variables: dict[str, Any] = {}


class CreateCampaignRequest(BaseModel):
    name: str
    subject: str
    body: str
    delay_seconds: int = 30
    recipients: list[RecipientInput]

    @field_validator("delay_seconds")
    @classmethod
    def min_delay(cls, v: int) -> int:
        if v < settings.bulk_email_min_delay_seconds:
            raise ValueError(f"Minimum delay is {settings.bulk_email_min_delay_seconds} seconds")
        return v

    @field_validator("recipients")
    @classmethod
    def max_recipients(cls, v: list) -> list:
        if len(v) > settings.rate_limit_bulk_email_per_campaign:
            raise ValueError(f"Max {settings.rate_limit_bulk_email_per_campaign} recipients per campaign")
        return v
