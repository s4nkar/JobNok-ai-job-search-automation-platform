"""Unit tests for cover_letter.service's _session_display_label — a pure
function, no DB/mocking needed. Simpler than resume_tailor's version since
company/role are always literal form fields on a saved cover letter session
(never AI-guessed), so there's no opportunity/application fallback lookup."""

from app.modules.cover_letter.models import CoverLetterSession
from app.modules.cover_letter.service import _session_display_label


def _session(**overrides) -> CoverLetterSession:
    base = {"title": None, "company": "Acme Corp", "role": "Senior Software Engineer"}
    base.update(overrides)
    return CoverLetterSession(**base)


def test_display_label_prefers_user_set_title():
    session = _session(title="My Google Letter")
    assert _session_display_label(session) == "My Google Letter"


def test_display_label_falls_back_to_role_at_company():
    session = _session(title=None)
    assert _session_display_label(session) == "Senior Software Engineer at Acme Corp"


def test_display_label_ignores_blank_title():
    session = _session(title="")
    assert _session_display_label(session) == "Senior Software Engineer at Acme Corp"
