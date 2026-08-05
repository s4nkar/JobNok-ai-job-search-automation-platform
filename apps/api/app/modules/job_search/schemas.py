"""Request/response models for the job-search feature."""

from typing import Any
from pydantic import BaseModel, HttpUrl, field_validator


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
