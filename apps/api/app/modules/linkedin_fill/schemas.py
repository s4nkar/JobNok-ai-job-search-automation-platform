"""Request/response models for the linkedin-fill feature."""

from pydantic import BaseModel, field_validator


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
