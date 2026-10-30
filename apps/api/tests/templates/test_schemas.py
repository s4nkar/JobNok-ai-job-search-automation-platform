"""Unit tests for templates.schemas — pure Pydantic validation, no I/O, no
mocking needed. name/content were previously unbounded (a DoS vector per
CLAUDE.md's input-length rule) and category accepted any string regardless
of the frontend's Zod enum; these tests pin the bounds that fix both."""

import pytest
from pydantic import ValidationError

from app.modules.templates.schemas import TemplateIn, TemplateUpdate


def _valid_kwargs(**overrides):
    base = {"name": "Recruiter Outreach", "category": "Cold DM - Recruiter", "content": "Hi {{name}}, I'd love to connect."}
    base.update(overrides)
    return base


def test_template_in_accepts_valid_input():
    req = TemplateIn(**_valid_kwargs())
    assert req.name == "Recruiter Outreach"
    assert req.category == "Cold DM - Recruiter"


@pytest.mark.parametrize("category", [
    "Cold DM - Recruiter", "Cold DM - Hiring Manager", "Follow-Up", "Referral Ask", "Email Outreach", "Custom",
])
def test_template_in_accepts_every_real_category(category):
    TemplateIn(**_valid_kwargs(category=category))


def test_template_in_rejects_unknown_category():
    with pytest.raises(ValidationError):
        TemplateIn(**_valid_kwargs(category="LinkedIn"))


def test_template_in_rejects_too_short_name():
    with pytest.raises(ValidationError):
        TemplateIn(**_valid_kwargs(name="x"))


def test_template_in_enforces_name_max_length():
    with pytest.raises(ValidationError):
        TemplateIn(**_valid_kwargs(name="x" * 101))
    TemplateIn(**_valid_kwargs(name="x" * 100))


def test_template_in_rejects_too_short_content():
    with pytest.raises(ValidationError):
        TemplateIn(**_valid_kwargs(content="short"))


def test_template_in_enforces_content_max_length():
    with pytest.raises(ValidationError):
        TemplateIn(**_valid_kwargs(content="x" * 5001))
    TemplateIn(**_valid_kwargs(content="x" * 5000))


def test_template_update_allows_all_fields_omitted():
    req = TemplateUpdate()
    assert req.name is None
    assert req.category is None
    assert req.content is None


def test_template_update_enforces_same_bounds_as_create():
    with pytest.raises(ValidationError):
        TemplateUpdate(name="x" * 101)
    with pytest.raises(ValidationError):
        TemplateUpdate(content="x" * 5001)
    with pytest.raises(ValidationError):
        TemplateUpdate(category="LinkedIn")


def test_template_update_has_no_use_count_field():
    # use_count must only ever change via the atomic POST /{id}/use
    # endpoint - never a client-supplied value on a PUT. Confirms the
    # field was actually removed, not just made optional.
    assert "use_count" not in TemplateUpdate.model_fields
