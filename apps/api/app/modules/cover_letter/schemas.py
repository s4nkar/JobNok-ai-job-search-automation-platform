"""Request/response models for the cover-letter feature."""

from pydantic import BaseModel, Field


class CoverLetterRequest(BaseModel):
    # Every field was previously unbounded str — a direct DoS vector
    # (CLAUDE.md: "Input length limits: every text field has a max length...
    # Unbounded inputs are a DoS vector") and, for resume_text/selling_points
    # specifically, an unbounded prompt-injection/cost surface since both are
    # embedded directly into the LLM prompt with no truncation anywhere in
    # this module. Bounds mirror the frontend's Zod schema (apps/web's
    # cover-letter page) — kept in sync by hand, same pattern CLAUDE.md
    # documents for every other tool's Form(..., max_length=...) fields.
    company: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=200)
    selling_points: str = Field(..., min_length=20, max_length=3000)
    resume_text: str | None = Field(None, max_length=8000)
    # Generation auto-persists (see routes.py) rather than requiring an
    # explicit Save click - a forgotten click previously meant a full
    # regeneration (AI cost + user time) to recover lost content. When a
    # tracked job is linked, the backend upserts into the single existing
    # session for that job (ownership re-verified server-side) instead of
    # creating a duplicate. With no job link, session_id lets the frontend
    # continue updating the same ad-hoc row across regenerations within one
    # browser visit instead of piling up a new row per click.
    opportunity_id: str | None = None
    job_search_application_id: str | None = None
    session_id: str | None = None


class CoverLetterPdfRequest(BaseModel):
    # The letter as currently shown/edited in the frontend's textarea — this
    # endpoint renders exactly that text, verbatim, no AI call involved.
    # 5000 chars is generous headroom over the ~350-word target the
    # generation prompt asks for (even a heavily hand-expanded letter is
    # very unlikely to exceed this).
    content: str = Field(..., min_length=1, max_length=5000)


# ── Saved sessions ("My Docs") ────────────────────────────────────
# No save/create request here - persistence is folded into
# CoverLetterRequest/routes.py's generation handler (auto-save, see its
# comment above). Only read/rename remain as their own endpoints.

class CoverLetterSessionSummary(BaseModel):
    id: str
    title: str | None
    display_label: str
    created_at: str
    source_opportunity_id: str | None = None
    source_application_id: str | None = None


class CoverLetterSessionListResponse(BaseModel):
    sessions: list[CoverLetterSessionSummary]


class CoverLetterSessionDetail(BaseModel):
    id: str
    title: str | None
    company: str
    role: str
    selling_points: str
    resume_text: str | None
    content: str
    created_at: str
    source_opportunity_id: str | None = None
    source_application_id: str | None = None


class CoverLetterTitleUpdateRequest(BaseModel):
    title: str = Field(..., max_length=200)
