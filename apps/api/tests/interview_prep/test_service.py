"""Unit tests for interview_prep.service's _session_display_label — a pure
function, no DB/mocking needed."""

from app.modules.interview_prep.models import InterviewPrepSession
from app.modules.interview_prep.service import _session_display_label


def _session(**overrides) -> InterviewPrepSession:
    base = {"title": None, "company": None, "role": None, "result": {}}
    base.update(overrides)
    return InterviewPrepSession(**base)


def test_display_label_prefers_user_set_title():
    session = _session(title="My Prep Notes")
    assert _session_display_label(session) == "My Prep Notes"


def test_display_label_uses_role_at_company_when_both_known():
    session = _session(company="Acme Corp", role="AI Engineer")
    assert _session_display_label(session) == "AI Engineer at Acme Corp"


def test_display_label_falls_back_to_role_family_from_result():
    session = _session(result={"role_assessment": {"role_family": "Backend Engineer"}})
    assert _session_display_label(session) == "Backend Engineer Interview Kit"


def test_display_label_falls_back_to_generic_label_when_nothing_known():
    session = _session()
    assert _session_display_label(session) == "Interview Prep Kit"


def test_display_label_ignores_blank_title():
    session = _session(title="", company="Acme Corp", role="AI Engineer")
    assert _session_display_label(session) == "AI Engineer at Acme Corp"


def test_display_label_requires_both_company_and_role():
    session = _session(company="Acme Corp", role=None, result={"role_assessment": {"role_family": "Backend Engineer"}})
    assert _session_display_label(session) == "Backend Engineer Interview Kit"
