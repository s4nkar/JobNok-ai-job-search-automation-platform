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
