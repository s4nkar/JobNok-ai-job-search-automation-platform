"""Request/response models for the startup-scout feature."""

from pydantic import BaseModel, Field, field_validator

# Matches engine.py's _STAGE_CANONICAL/_STAGE_NORMALISE vocabulary - the
# full set of stages the scraper/normalizer actually recognizes, a superset
# of the 5 the frontend currently exposes as filter buttons (pre-seed, seed,
# series-a/b/c) so a future frontend addition (series-d/e, angel) doesn't
# need a backend schema change too.
_VALID_FUNDING_STAGES = {"angel", "pre-seed", "seed", "series-a", "series-b", "series-c", "series-d", "series-e"}


class ScoutSearchRequest(BaseModel):
    location: str = Field(min_length=1, max_length=300)
    funding_stages: list[str] = Field(default_factory=list, max_length=8)
    industry: str = Field(default="", max_length=100)
    size_range: str = Field(default="", max_length=50)
    limit: int = Field(default=50, ge=10, le=200)

    @field_validator("funding_stages")
    @classmethod
    def validate_funding_stages(cls, value: list[str]) -> list[str]:
        for stage in value:
            if stage not in _VALID_FUNDING_STAGES:
                raise ValueError(f"Unknown funding stage: {stage!r}")
        return value


class SaveCompanyRequest(BaseModel):
    name: str = Field(max_length=300)
    description: str = Field(default="", max_length=2000)
    what_they_do: str = Field(default="", max_length=1000)
    funding_stage: str = Field(default="", max_length=50)
    size_range: str = Field(default="", max_length=50)
    location: str = Field(default="", max_length=300)
    website: str = Field(default="", max_length=500)
    linkedin_url: str = Field(default="", max_length=500)
    source: str = Field(default="web_scrape", max_length=100)

    @field_validator("website")
    @classmethod
    def validate_website(cls, value: str) -> str:
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("website must be an http or https URL")
        return value
