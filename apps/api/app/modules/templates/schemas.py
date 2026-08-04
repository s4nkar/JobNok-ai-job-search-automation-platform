"""Request/response models for the templates feature (resume-template CRUD)."""

from pydantic import BaseModel, field_validator
from typing import Optional


class TemplateIn(BaseModel):
    name: str
    category: str
    content: str

    @field_validator("name")
    @classmethod
    def name_min(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("name must be at least 2 characters")
        return v

    @field_validator("content")
    @classmethod
    def content_min(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("content must be at least 10 characters")
        return v


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None
