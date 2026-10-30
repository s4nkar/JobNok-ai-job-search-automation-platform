"""Request/response models for the interview-prep feature."""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

logger = logging.getLogger(__name__)

# Mirrors resume_tailor's _JD_TEXT_MAX_CHARS bound - same DoS/prompt-cost
# reasoning (CLAUDE.md: every text field needs a max length).
_JD_MAX_CHARS = 12000
_QUESTION_MAX_CHARS = 500


class InterviewPrepRequest(BaseModel):
    job_description: str = Field(..., min_length=20, max_length=_JD_MAX_CHARS)
    # Trusted context from an already-known Startup Hunt lead or tracked
    # application - when present, takes precedence over whatever the model
    # might guess from the JD text alone (reduces company-name
    # hallucination risk, since this came from our own DB, not a free-text
    # extraction over a possibly company-less recruiter post).
    company: str | None = Field(None, max_length=200)
    role: str | None = Field(None, max_length=200)
    # Generation auto-persists (see service.py::resolve_session) rather
    # than requiring an explicit Save click - a forgotten click previously
    # meant a full regeneration (AI cost + user time) to recover lost
    # content. When a tracked job is linked, the backend upserts into the
    # single existing session for that job instead of creating a
    # duplicate. With no job link, session_id lets the frontend continue
    # updating the same ad-hoc row across regenerations within one browser
    # visit instead of piling up a new row per click.
    opportunity_id: str | None = None
    job_search_application_id: str | None = None
    session_id: str | None = None


class InterviewRegenerateRequest(BaseModel):
    job_description: str = Field(..., min_length=20, max_length=_JD_MAX_CHARS)
    question: str = Field(..., min_length=1, max_length=_QUESTION_MAX_CHARS)
    # When present, the regenerated answer is written back into that saved
    # session's result.questions[question_index] - otherwise a saved kit
    # would silently drift out of sync with what the user sees after a
    # regenerate. Both optional: if either is missing (e.g. the question
    # set was never saved, which shouldn't happen under auto-save but is
    # not assumed), the regenerated answer is still returned, just not
    # persisted anywhere.
    session_id: str | None = None
    question_index: int | None = Field(None, ge=0)


# ── Response shape — validates generate_interview_questions' LLM output ──
# response_format=json_object (provider.py) only guarantees syntactically
# valid JSON, not the right shape - same reasoning as resume_tailor's
# CvDataSchema/validate_cv_data: a malformed field shouldn't discard the
# whole response, just fall back to that field's default.

class RoleAssessmentSchema(BaseModel):
    seniority: Literal["junior", "mid", "senior", "unclear"] = "unclear"
    role_family: str = ""
    likely_rounds: list[str] = Field(default_factory=list)
    company_context: str | None = None
    dsa_likely: bool = False
    system_design_likely: bool = False


class InterviewQuestionSchema(BaseModel):
    question: str = ""
    # Free text, not a Literal - this is a cosmetic display tag only (the
    # frontend just renders it as a badge, nothing branches on its exact
    # value), unlike seniority/dsa_likely/system_design_likely below which
    # DO gate behavior and must stay strict. A Literal here previously
    # caused a real failure: the prompt's own mix instruction asks for
    # "2 motivational" questions, but "Motivational" wasn't in the allowed
    # set, so one mismatched tag invalidated the entire 10-question list
    # down to [] - a cosmetic label mismatch shouldn't cost the whole
    # response.
    framework: str = "Behavioral"
    answer_framework: str = ""
    tips: list[str] = Field(default_factory=list)


class TechnicalPrepQuestionSchema(BaseModel):
    question: str = ""
    approach: str = ""


class InterviewPrepResponseSchema(BaseModel):
    role_assessment: RoleAssessmentSchema = Field(default_factory=RoleAssessmentSchema)
    questions: list[InterviewQuestionSchema] = Field(default_factory=list)
    dsa_questions: list[TechnicalPrepQuestionSchema] = Field(default_factory=list)
    system_design_questions: list[TechnicalPrepQuestionSchema] = Field(default_factory=list)


class RegenerateAnswerSchema(BaseModel):
    answer_framework: str = ""
    tips: list[str] = Field(default_factory=list)


def _validate_against_schema(raw: dict[str, Any], schema_cls: type[BaseModel]) -> dict[str, Any]:
    """Field-by-field lenient validation - a single malformed top-level
    field falls back to its own default instead of rejecting the whole
    result. Generic over any of this module's response schemas (mirrors
    resume_tailor/schemas.py::validate_cv_data, generalized since this
    module validates more than one shape)."""
    result: dict[str, Any] = {}
    for name, field in schema_cls.model_fields.items():
        adapter = TypeAdapter(field.annotation)
        default = field.get_default(call_default_factory=True)
        if isinstance(default, BaseModel):
            default = default.model_dump(mode="json")
        value = raw.get(name, default)
        try:
            validated = adapter.validate_python(value)
            result[name] = adapter.dump_python(validated, mode="json")
        except ValidationError as exc:
            logger.warning("%s field %r failed schema validation (%s) — using default", schema_cls.__name__, name, exc)
            result[name] = default
    return result


def validate_interview_response(raw: dict[str, Any]) -> dict[str, Any]:
    return _validate_against_schema(raw, InterviewPrepResponseSchema)


def validate_regenerate_response(raw: dict[str, Any]) -> dict[str, Any]:
    return _validate_against_schema(raw, RegenerateAnswerSchema)


# ── Saved sessions ("My Docs") ────────────────────────────────────
# No create/save request here - persistence is folded into
# InterviewPrepRequest/service.py::resolve_session (auto-save, see that
# field's comment above). Only read/rename remain as their own endpoints.

class InterviewPrepSessionSummary(BaseModel):
    id: str
    title: str | None
    display_label: str
    question_count: int
    created_at: str
    source_opportunity_id: str | None = None
    source_application_id: str | None = None


class InterviewPrepSessionListResponse(BaseModel):
    sessions: list[InterviewPrepSessionSummary]


class InterviewPrepSessionDetail(BaseModel):
    id: str
    title: str | None
    job_description: str
    company: str | None
    role: str | None
    result: dict[str, Any]
    created_at: str
    source_opportunity_id: str | None = None
    source_application_id: str | None = None


class InterviewPrepTitleUpdateRequest(BaseModel):
    title: str = Field(..., max_length=200)
