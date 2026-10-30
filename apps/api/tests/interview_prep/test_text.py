"""Unit tests for interview_prep.text — pure dash-class normalization,
no I/O, no mocking needed. Mirrors tests/cover_letter/test_text.py's
coverage for the same character class."""

from app.modules.interview_prep.text import strip_dashes, strip_dashes_deep


def test_strip_dashes_replaces_em_and_en_dash():
    assert strip_dashes("end—to—end") == "end-to-end"
    assert strip_dashes("end–to–end") == "end-to-end"


def test_strip_dashes_replaces_non_breaking_hyphen():
    assert strip_dashes("end‑to‑end") == "end-to-end"


def test_strip_dashes_leaves_plain_hyphen_untouched():
    assert strip_dashes("a-b-c") == "a-b-c"


def test_strip_dashes_deep_handles_nested_structure():
    value = {
        "question": "Tell me about a time — specifically",
        "tips": ["be specific — concise", "use STAR"],
        "nested": {"approach": "two pointers — O(n)"},
        "count": 3,
        "ok": True,
        "none": None,
    }
    result = strip_dashes_deep(value)
    assert result["question"] == "Tell me about a time - specifically"
    assert result["tips"] == ["be specific - concise", "use STAR"]
    assert result["nested"]["approach"] == "two pointers - O(n)"
    assert result["count"] == 3
    assert result["ok"] is True
    assert result["none"] is None


def test_strip_dashes_deep_handles_list_of_dicts():
    value = [{"question": "a — b"}, {"question": "c"}]
    result = strip_dashes_deep(value)
    assert result == [{"question": "a - b"}, {"question": "c"}]
