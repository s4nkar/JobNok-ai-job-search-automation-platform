"""Request/response models for the interview-prep feature."""

from pydantic import BaseModel


class InterviewPrepRequest(BaseModel):
    job_description: str


class InterviewRegenerateRequest(BaseModel):
    job_description: str
    question: str
