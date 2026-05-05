"""Pydantic request/response models for all FastAPI endpoints.

All inputs validated here — never trust raw request data.
"""

from pydantic import BaseModel, HttpUrl, field_validator
from typing import Any


# ── Scraping ─────────────────────────────────────────────────────

class ScrapeLinkedInRequest(BaseModel):
    linkedin_url: str

    @field_validator("linkedin_url")
    @classmethod
    def must_be_linkedin(cls, v: str) -> str:
        if "linkedin.com" not in v:
            raise ValueError("URL must be a LinkedIn URL")
        return v


class ScrapeLinkedInResponse(BaseModel):
    data: dict
    cached: bool


# ── AI Tools ─────────────────────────────────────────────────────

class ResumeTailorRequest(BaseModel):
    job_description: str


class CoverLetterRequest(BaseModel):
    company: str
    role: str
    selling_points: str
    resume_text: str | None = None


class InterviewPrepRequest(BaseModel):
    job_description: str


class InterviewRegenerateRequest(BaseModel):
    job_description: str
    question: str


class SalaryResearchRequest(BaseModel):
    job_title: str
    location: str


# ── Email ─────────────────────────────────────────────────────────

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
        from lib.config import settings
        if v < settings.bulk_email_min_delay_seconds:
            raise ValueError(f"Minimum delay is {settings.bulk_email_min_delay_seconds} seconds")
        return v

    @field_validator("recipients")
    @classmethod
    def max_recipients(cls, v: list) -> list:
        from lib.config import settings
        if len(v) > settings.rate_limit_bulk_email_per_campaign:
            raise ValueError(f"Max {settings.rate_limit_bulk_email_per_campaign} recipients per campaign")
        return v
