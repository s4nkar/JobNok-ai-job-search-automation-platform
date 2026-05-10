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


class JobSearchRequest(BaseModel):
    query: str
    location: str
    country: str | None = None
    posted_within_hours: int | None = 24
    result_limit: int = 10
    remote_only: bool = False
    preferences_prompt: str | None = None

    @field_validator("query", "location")
    @classmethod
    def min_text_length(cls, v: str) -> str:
        value = v.strip()
        if len(value) < 2:
            raise ValueError("Must be at least 2 characters")
        return value

    @field_validator("country")
    @classmethod
    def normalize_country(cls, v: str | None) -> str | None:
        return v.strip() if v else None

    @field_validator("posted_within_hours")
    @classmethod
    def validate_posted_hours(cls, v: int | None) -> int | None:
        if v is not None and (v < 1 or v > 720):
            raise ValueError("posted_within_hours must be between 1 and 720")
        return v

    @field_validator("result_limit")
    @classmethod
    def validate_result_limit(cls, v: int) -> int:
        if v < 1 or v > 50:
            raise ValueError("result_limit must be between 1 and 50")
        return v


class JobSearchApplicationCreateRequest(BaseModel):
    job_url: HttpUrl
    job_url_canonical: HttpUrl | None = None
    source_name: str
    external_job_id: str | None = None
    company: str
    role: str
    location: str
    posted_at: str | None = None
    applied_at: str | None = None
    application_status: str = "applied"
    citation_payload: dict[str, Any]
    search_context: dict[str, Any] = {}

    @field_validator("source_name", "company", "role", "location")
    @classmethod
    def require_text(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Field is required")
        return value

    @field_validator("application_status")
    @classmethod
    def validate_create_status(cls, v: str) -> str:
        value = v.strip()
        if value not in {"saved", "applied", "skipped"}:
            raise ValueError("application_status must be saved, applied, or skipped")
        return value

    @field_validator("posted_at", "applied_at")
    @classmethod
    def validate_datetimes(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        text = v.strip().replace("Z", "+00:00")
        try:
            from datetime import datetime
            datetime.fromisoformat(text)
        except ValueError:
            raise ValueError("Must be a valid ISO 8601 datetime")
        return text


class JobSearchApplicationUpdateRequest(BaseModel):
    application_status: str
    applied_at: str | None = None

    @field_validator("application_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        value = v.strip()
        if value not in {"saved", "applied", "skipped"}:
            raise ValueError("application_status must be saved, applied, or skipped")
        return value

    @field_validator("applied_at")
    @classmethod
    def validate_optional_applied_at(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        text = v.strip().replace("Z", "+00:00")
        try:
            from datetime import datetime
            datetime.fromisoformat(text)
        except ValueError:
            raise ValueError("Must be a valid ISO 8601 datetime")
        return text


class StartupHuntSearchRequest(BaseModel):
    query: str
    location: str = "Germany"
    country: str | None = "Germany"
    posted_within_hours: int | None = 72
    result_limit: int = 15
    include_seeded_sources: bool = False
    remote_only: bool = False
    direct_links_only: bool = False
    english_friendly_only: bool = False
    company_stage: str | None = None
    strategy_prompt: str | None = None
    seeded_limit: int = 0
    crawler_limit: int = 20
    startupmap_limit: int = 10
    web_limit: int = 10
    indeed_limit: int = 10
    apify_limit: int = 10
    ats_limit: int = 10

    @field_validator("query", "location")
    @classmethod
    def validate_required_text(cls, v: str) -> str:
        value = v.strip()
        if len(value) < 2:
            raise ValueError("Must be at least 2 characters")
        return value

    @field_validator("country", "company_stage", "strategy_prompt")
    @classmethod
    def normalize_optional_text(cls, v: str | None) -> str | None:
        return v.strip() if v and v.strip() else None

    @field_validator("posted_within_hours")
    @classmethod
    def validate_optional_hours(cls, v: int | None) -> int | None:
        if v is not None and (v < 1 or v > 1440):
            raise ValueError("posted_within_hours must be between 1 and 1440")
        return v

    @field_validator("result_limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if v < 1 or v > 50:
            raise ValueError("result_limit must be between 1 and 50")
        return v

    @field_validator("seeded_limit", "crawler_limit", "startupmap_limit", "web_limit", "indeed_limit", "apify_limit", "ats_limit")
    @classmethod
    def validate_source_limit(cls, v: int) -> int:
        if v < 0 or v > 50:
            raise ValueError("Source limits must be between 0 and 50")
        return v


class StartupHuntOpportunityCreateRequest(BaseModel):
    company_name: str
    company_domain: str | None = None
    company_website_url: HttpUrl | None = None
    company_careers_url: HttpUrl | None = None
    role_title: str
    location: str
    country: str | None = None
    source_name: str
    source_type: str
    direct_apply_url: HttpUrl | None = None
    canonical_job_url: HttpUrl | None = None
    portal_job_url: HttpUrl | None = None
    posted_at: str | None = None
    discovered_at: str | None = None
    opportunity_kind: str = "job"
    opportunity_status: str = "saved"
    score_total: float = 0
    score_labels: list[str] = []
    score_reasons: list[str] = []
    citation_payload: dict[str, Any]
    company_payload: dict[str, Any] = {}
    search_context: dict[str, Any] = {}
    contacts: list[dict[str, Any]] = []

    @field_validator(
        "company_name",
        "role_title",
        "location",
        "source_name",
        "source_type",
        "opportunity_kind",
        "opportunity_status",
    )
    @classmethod
    def validate_non_empty_text(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Field is required")
        return value

    @field_validator("country", "company_domain")
    @classmethod
    def normalize_nullable_text(cls, v: str | None) -> str | None:
        return v.strip() if v and v.strip() else None

    @field_validator("posted_at", "discovered_at")
    @classmethod
    def validate_optional_datetime(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        text = v.strip().replace("Z", "+00:00")
        try:
            from datetime import datetime
            datetime.fromisoformat(text)
        except ValueError:
            raise ValueError("Must be a valid ISO 8601 datetime")
        return text

    @field_validator("opportunity_kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        if v not in {"job", "outreach_lead"}:
            raise ValueError("opportunity_kind must be job or outreach_lead")
        return v

    @field_validator("opportunity_status")
    @classmethod
    def validate_opportunity_status(cls, v: str) -> str:
        if v not in {"saved", "applied", "contacted", "skipped"}:
            raise ValueError("opportunity_status must be saved, applied, contacted, or skipped")
        return v


class StartupHuntOpportunityUpdateRequest(BaseModel):
    opportunity_status: str
    direct_apply_url: HttpUrl | None = None
    canonical_job_url: HttpUrl | None = None

    @field_validator("opportunity_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        value = v.strip()
        if value not in {"saved", "applied", "contacted", "skipped"}:
            raise ValueError("opportunity_status must be saved, applied, contacted, or skipped")
        return value


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
