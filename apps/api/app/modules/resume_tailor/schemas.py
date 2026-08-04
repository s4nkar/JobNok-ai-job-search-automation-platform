"""Request/response models for the resume-tailor feature."""

from pydantic import BaseModel


class ResumeTailorRequest(BaseModel):
    job_description: str
