"""Request/response models for the tracker feature."""

import datetime
from pydantic import BaseModel, field_validator
from typing import Optional


class ApplicationIn(BaseModel):
    company: str
    role: str
    applied_at: str
    status: str
    follow_up_date: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    notes: Optional[str] = None

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
