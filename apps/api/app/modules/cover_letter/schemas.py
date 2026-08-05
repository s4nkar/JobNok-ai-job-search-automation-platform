"""Request/response models for the cover-letter feature."""

from pydantic import BaseModel


class CoverLetterRequest(BaseModel):
    company: str
    role: str
    selling_points: str
    resume_text: str | None = None
