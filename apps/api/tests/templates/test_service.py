"""Unit tests for templates.service's extract_placeholders — a pure
function, no DB/mocking needed."""

from app.modules.templates.service import extract_placeholders


def test_extract_placeholders_finds_all_unique_names():
    content = "Hi {{name}}, I saw the {{job_title}} role at {{company}}."
    assert extract_placeholders(content) == ["name", "job_title", "company"]


def test_extract_placeholders_dedupes_repeated_names():
    content = "Hi {{name}}, {{name}} is a great name."
    assert extract_placeholders(content) == ["name"]


def test_extract_placeholders_preserves_first_occurrence_order():
    content = "{{c}} then {{a}} then {{b}} then {{a}} again"
    assert extract_placeholders(content) == ["c", "a", "b"]


def test_extract_placeholders_returns_empty_list_when_none_present():
    assert extract_placeholders("Plain text with no placeholders at all.") == []


def test_extract_placeholders_strips_whitespace_inside_braces():
    content = "Hi {{ name }}, welcome to {{company }}."
    assert extract_placeholders(content) == ["name", "company"]
