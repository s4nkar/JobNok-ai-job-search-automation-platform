"""Request/response models for the salary feature."""

from pydantic import BaseModel


class SalaryResearchRequest(BaseModel):
    job_title: str
    location: str
