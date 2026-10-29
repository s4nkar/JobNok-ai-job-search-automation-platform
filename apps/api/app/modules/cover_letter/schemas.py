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


class CoverLetterPdfRequest(BaseModel):
    # The letter as currently shown/edited in the frontend's textarea — this
    # endpoint renders exactly that text, verbatim, no AI call involved.
    # 5000 chars is generous headroom over the ~350-word target the
    # generation prompt asks for (even a heavily hand-expanded letter is
    # very unlikely to exceed this).
    content: str = Field(..., min_length=1, max_length=5000)


# ── Saved sessions ("My Docs") ────────────────────────────────────
# Explicit save only (not auto-saved on every generation) - see
# sessions_routes.py for why. Bounds mirror CoverLetterRequest/
# CoverLetterPdfRequest above, since a save always carries the same fields
# that produced the letter plus the letter itself.

class CoverLetterSaveRequest(BaseModel):
    company: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=200)
    selling_points: str = Field(..., min_length=20, max_length=3000)
    resume_text: str | None = Field(None, max_length=8000)
    content: str = Field(..., min_length=1, max_length=5000)
    opportunity_id: str | None = None
    job_search_application_id: str | None = None


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
