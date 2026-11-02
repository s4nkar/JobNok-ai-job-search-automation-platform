"""Request/response models for the tracker feature."""

import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Mirrors the frontend's ApplicationStatus union (apps/web/lib/types.ts) -
# kept in sync by hand, same pattern CLAUDE.md documents for every other
# Zod/Pydantic pair. Previously a bare `str` accepted any value regardless
# of what the frontend's status dropdown actually allowed.
ApplicationStatus = Literal["Applied", "Phone Screen", "Interview", "Offer", "Rejected", "Withdrawn"]

# Previously unbounded (CLAUDE.md: "Input length limits: every text field
# has a max length... Unbounded inputs are a DoS vector") - company/role/
# notes had no ceiling at either the Pydantic or DB layer.
_COMPANY_MAX_LENGTH = 200
_ROLE_MAX_LENGTH = 200
_NOTES_MAX_LENGTH = 3000


class ApplicationIn(BaseModel):
    company: str = Field(..., min_length=1, max_length=_COMPANY_MAX_LENGTH)
    role: str = Field(..., min_length=1, max_length=_ROLE_MAX_LENGTH)
    applied_at: str
    status: ApplicationStatus
    follow_up_date: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    notes: Optional[str] = Field(None, max_length=_NOTES_MAX_LENGTH)

    @field_validator("applied_at")
    @classmethod
    def validate_applied_at(cls, v: str) -> str:
        try:
            datetime.date.fromisoformat(v)
        except ValueError:
            raise ValueError("applied_at must be ISO 8601 date (YYYY-MM-DD)")
        return v

    @field_validator("follow_up_date")
    @classmethod
    def validate_follow_up_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                datetime.date.fromisoformat(v)
            except ValueError:
                raise ValueError("follow_up_date must be ISO 8601 date (YYYY-MM-DD)")
        return v
