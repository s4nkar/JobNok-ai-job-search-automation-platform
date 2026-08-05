"""Request/response models for the startup-scout feature."""

from pydantic import BaseModel, field_validator


class ScoutSearchRequest(BaseModel):
    location: str
    funding_stages: list[str] = []
    industry: str = ""
    size_range: str = ""
    limit: int = 50


class SaveCompanyRequest(BaseModel):
    name: str
    description: str = ""
    what_they_do: str = ""
    funding_stage: str = ""
    size_range: str = ""
    location: str = ""
    website: str = ""
    linkedin_url: str = ""
    source: str = "web_scrape"

    @field_validator("website")
    @classmethod
    def validate_website(cls, value: str) -> str:
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("website must be an http or https URL")
        return value
