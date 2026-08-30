"""Request/response models for resume-tailor's session-based API.

cv_data is intentionally typed as a pass-through dict rather than fully
modeled: its shape already varies across 17 templates (some sections
optional depending on template/resume content), matching how the original
(pre-session) endpoints validated it — a plain JSON body, not a strict
Pydantic model. The session/analysis/ai fields around it, which are what
actually needs a stable contract, are fully modeled below.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MissingKeyword(BaseModel):
    keyword: str
    suggested_placement: str


class AnalysisPayload(BaseModel):
    match_score: int
    matched_keywords: list[str]
    missing_keywords: list[MissingKeyword]
    score_breakdown: dict[str, int] = Field(default_factory=dict)
    transferable_strengths: list[str] = Field(default_factory=list)
    critical_missing: list[str] = Field(default_factory=list)
    matches: list[dict[str, Any]] = Field(default_factory=list)
    degraded: bool = False


class BulletRewrite(BaseModel):
    original: str
    improved: str


class TailoringPayload(BaseModel):
    target_role: str = ""
    target_company: str = ""
    profile_headline: str = ""
    tailored_summary: str = ""
    bullet_rewrites: list[BulletRewrite] = Field(default_factory=list)
    summary: str = ""
    validation_flags: list[str] = Field(default_factory=list)


class AiStatusPayload(BaseModel):
    status: str  # "ok" | "degraded"
    provider: str | None = None


class TailorResponse(BaseModel):
    session_id: str
    status: str  # "ready" | "failed"
    analysis: AnalysisPayload
    tailoring: TailoringPayload | None = None
    ai: AiStatusPayload


class EditorResponse(BaseModel):
    cv_data: dict[str, Any]
    session_id: str
    template_id: str
    templates: list[dict[str, Any]]
    is_draft: bool = False


class TemplateListResponse(BaseModel):
    templates: list[dict[str, Any]]


class PreviewRequest(BaseModel):
    template_id: str
    cv_data: dict[str, Any]


class PdfRequest(BaseModel):
    template_id: str
    cv_data: dict[str, Any]
    opportunity_id: str | None = None


class DraftSaveRequest(BaseModel):
    cv_data: dict[str, Any]
