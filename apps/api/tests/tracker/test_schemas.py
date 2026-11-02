"""Unit tests for tracker.schemas — pure Pydantic validation, no I/O, no
mocking needed. company/role/notes were previously unbounded (a DoS vector
per CLAUDE.md's input-length rule) and status accepted any string
regardless of the frontend's dropdown; these tests pin the bounds that fix
both."""

import pytest
from pydantic import ValidationError

from app.modules.tracker.schemas import ApplicationIn


def _valid_kwargs(**overrides):
    base = {"company": "Acme Corp", "role": "Software Engineer", "applied_at": "2026-11-01", "status": "Applied"}
    base.update(overrides)
    return base


def test_application_in_accepts_valid_input():
    req = ApplicationIn(**_valid_kwargs())
    assert req.company == "Acme Corp"
    assert req.status == "Applied"
    assert req.notes is None


@pytest.mark.parametrize("status", [
    "Applied", "Phone Screen", "Interview", "Offer", "Rejected", "Withdrawn",
])
def test_application_in_accepts_every_real_status(status):
    ApplicationIn(**_valid_kwargs(status=status))


def test_application_in_rejects_unknown_status():
    with pytest.raises(ValidationError):
        ApplicationIn(**_valid_kwargs(status="Ghosted"))


def test_application_in_rejects_empty_required_fields():
    with pytest.raises(ValidationError):
        ApplicationIn(**_valid_kwargs(company=""))
    with pytest.raises(ValidationError):
        ApplicationIn(**_valid_kwargs(role=""))


def test_application_in_enforces_company_max_length():
    with pytest.raises(ValidationError):
        ApplicationIn(**_valid_kwargs(company="x" * 201))
    ApplicationIn(**_valid_kwargs(company="x" * 200))


def test_application_in_enforces_role_max_length():
    with pytest.raises(ValidationError):
        ApplicationIn(**_valid_kwargs(role="x" * 201))
    ApplicationIn(**_valid_kwargs(role="x" * 200))


def test_application_in_enforces_notes_max_length():
    with pytest.raises(ValidationError):
        ApplicationIn(**_valid_kwargs(notes="x" * 3001))
    ApplicationIn(**_valid_kwargs(notes="x" * 3000))


def test_application_in_rejects_malformed_applied_at():
    with pytest.raises(ValidationError):
        ApplicationIn(**_valid_kwargs(applied_at="11/01/2026"))


def test_application_in_rejects_malformed_follow_up_date():
    with pytest.raises(ValidationError):
        ApplicationIn(**_valid_kwargs(follow_up_date="not-a-date"))


def test_application_in_accepts_valid_follow_up_date():
    req = ApplicationIn(**_valid_kwargs(follow_up_date="2026-12-01"))
    assert req.follow_up_date == "2026-12-01"
