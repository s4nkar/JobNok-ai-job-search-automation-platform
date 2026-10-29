"""Unit tests for cover_letter.schemas — pure Pydantic validation, no I/O,
no mocking needed. Every field here was previously unbounded str (a DoS
vector per CLAUDE.md's input-length rule); these tests pin the bounds that
fix closed."""

import pytest
from pydantic import ValidationError

from app.modules.cover_letter.schemas import CoverLetterPdfRequest, CoverLetterRequest


def _valid_request_kwargs(**overrides):
    base = {
        "company": "Acme Corp",
        "role": "Senior Software Engineer",
        "selling_points": "Led a team of 4 engineers and shipped 3 major product launches on time.",
    }
    base.update(overrides)
    return base


def test_cover_letter_request_accepts_valid_input():
    req = CoverLetterRequest(**_valid_request_kwargs())
    assert req.company == "Acme Corp"
    assert req.resume_text is None


def test_cover_letter_request_resume_text_is_optional():
    req = CoverLetterRequest(**_valid_request_kwargs(resume_text="Some resume summary."))
    assert req.resume_text == "Some resume summary."


@pytest.mark.parametrize("field,value", [
    ("company", ""),
    ("role", ""),
])
def test_cover_letter_request_rejects_empty_required_fields(field, value):
    with pytest.raises(ValidationError):
        CoverLetterRequest(**_valid_request_kwargs(**{field: value}))


def test_cover_letter_request_rejects_too_short_selling_points():
    with pytest.raises(ValidationError):
        CoverLetterRequest(**_valid_request_kwargs(selling_points="Too short."))


@pytest.mark.parametrize("field,limit", [
    ("company", 200),
    ("role", 200),
])
def test_cover_letter_request_enforces_max_length(field, limit):
    with pytest.raises(ValidationError):
        CoverLetterRequest(**_valid_request_kwargs(**{field: "x" * (limit + 1)}))
    # exactly at the limit must still pass
    CoverLetterRequest(**_valid_request_kwargs(**{field: "x" * limit}))


def test_cover_letter_request_selling_points_max_length():
    with pytest.raises(ValidationError):
        CoverLetterRequest(**_valid_request_kwargs(selling_points="x" * 3001))
    CoverLetterRequest(**_valid_request_kwargs(selling_points="x" * 3000))


def test_cover_letter_request_resume_text_max_length():
    with pytest.raises(ValidationError):
        CoverLetterRequest(**_valid_request_kwargs(resume_text="x" * 8001))
    CoverLetterRequest(**_valid_request_kwargs(resume_text="x" * 8000))


def test_cover_letter_pdf_request_accepts_valid_content():
    req = CoverLetterPdfRequest(content="Dear Hiring Manager, I am writing to apply.")
    assert req.content.startswith("Dear")


def test_cover_letter_pdf_request_rejects_empty_content():
    with pytest.raises(ValidationError):
        CoverLetterPdfRequest(content="")


def test_cover_letter_pdf_request_enforces_max_length():
    with pytest.raises(ValidationError):
        CoverLetterPdfRequest(content="x" * 5001)
    CoverLetterPdfRequest(content="x" * 5000)
