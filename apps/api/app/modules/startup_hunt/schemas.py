"""Request/response models for the startup-hunt feature."""

from typing import Any
from pydantic import BaseModel, HttpUrl, field_validator

from app.modules.startup_hunt.engine import ALLOWED_SOURCE_TYPES


class StartupHuntSearchRequest(BaseModel):
    query: str
    location: str = "Germany"
    country: str | None = "Germany"
    posted_within_hours: int | None = 168
    result_limit: int = 25
    include_seeded_sources: bool = False
    remote_only: bool = False
    direct_links_only: bool = False
    english_friendly_only: bool = False
    company_stage: str | None = None
    strategy_prompt: str | None = None
    crawler_enabled: bool = False
    startupmap_enabled: bool = False
    web_enabled: bool = False
    indeed_enabled: bool = False
    theirstack_enabled: bool = True
    apify_enabled: bool = False
    ats_enabled: bool = True
    seeded_limit: int = 0
    crawler_limit: int = 0
    startupmap_limit: int = 0
    web_limit: int = 0
    indeed_limit: int = 0
    theirstack_limit: int = 15
    apify_limit: int = 0
    ats_limit: int = 15

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

    @field_validator("seeded_limit", "crawler_limit", "startupmap_limit", "web_limit", "indeed_limit", "theirstack_limit", "apify_limit", "ats_limit")
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


class StartupHuntSourceIn(BaseModel):
    """A user's own ATS/company source to merge into their startup-hunt searches."""

    type: str
    name: str
    company: str | None = None
    slug: str | None = None
    url: HttpUrl | None = None
    metadata: dict[str, Any] = {}

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        value = v.strip().lower()
        if value not in ALLOWED_SOURCE_TYPES:
            raise ValueError(f"type must be one of: {', '.join(sorted(ALLOWED_SOURCE_TYPES))}")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("name is required")
        return value

    @field_validator("company")
    @classmethod
    def normalize_company(cls, v: str | None) -> str | None:
        return v.strip() if v and v.strip() else None

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, v: str | None) -> str | None:
        return v.strip() if v and v.strip() else None
