"""Unit tests for resume_tailor.chunker — pure regex/heuristic functions,
no I/O, no mocking needed."""

from app.modules.resume_tailor.chunker import (
    chunk_jd,
    chunk_resume,
    chunks_from_dicts,
    chunks_to_dicts,
    clean_jd_text,
)


def test_chunk_resume_splits_bullets_by_glyph():
    text = "Experience\n• Built a thing\n• Shipped another thing"
    bullets = [c for c in chunk_resume(text) if c.kind == "bullet"]
    assert [c.text for c in bullets] == ["Built a thing", "Shipped another thing"]
    assert bullets[0].section == "experience"


def test_chunk_resume_absorbs_wrapped_continuation_lines():
    text = "Experience\n• Built a thing\nthat scaled to a million users\n• Shipped another thing"
    bullets = [c for c in chunk_resume(text) if c.kind == "bullet"]
    assert bullets[0].text == "Built a thing that scaled to a million users"
    assert bullets[1].text == "Shipped another thing"


def test_chunk_resume_explodes_comma_separated_skills():
    text = "Skills\nPython, TypeScript, SQL"
    skills = [c for c in chunk_resume(text) if c.kind == "skill"]
    assert [c.text for c in skills] == ["Python", "TypeScript", "SQL"]


def test_chunk_resume_empty_text_returns_empty_list():
    assert chunk_resume("") == []


def test_chunk_resume_very_long_section_produces_many_chunks():
    bullets_text = "\n".join(f"• Achievement number {i} exceeding target significantly" for i in range(50))
    text = "Experience\n" + bullets_text
    bullets = [c for c in chunk_resume(text) if c.kind == "bullet"]
    assert len(bullets) == 50


def test_chunk_jd_detects_requirement_vs_responsibility_sections():
    text = "Responsibilities:\n- Own the roadmap\nRequirements:\n- 5 years experience"
    chunks = chunk_jd(text)
    responsibilities = [c.text for c in chunks if c.kind == "responsibility"]
    requirements = [c.text for c in chunks if c.kind == "requirement"]
    assert "Own the roadmap" in responsibilities
    assert "5 years experience" in requirements


def test_chunk_jd_prose_only_splits_on_sentence_boundaries():
    text = "Requirements:\nYou must know Python. You must know SQL. Nice to have Docker experience."
    texts = [c.text for c in chunk_jd(text)]
    assert "You must know Python." in texts
    assert "You must know SQL." in texts
    assert "Nice to have Docker experience." in texts


def test_chunk_jd_empty_text_returns_empty_list():
    assert chunk_jd("") == []


def test_clean_jd_text_strips_tracker_metadata_and_boilerplate():
    text = "Requirements:\n- Python\nRole Signals:\n• Matched Role Keywords: Python, SQL"
    cleaned = clean_jd_text(text)
    assert "Role Signals" not in cleaned
    assert "Requirements" in cleaned


def test_clean_jd_text_preserves_requirements_after_benefits_section():
    text = "About the role\nBenefits:\n- Free coffee\nRequirements:\n- 5 years Python"
    cleaned = clean_jd_text(text)
    assert "Requirements" in cleaned
    assert "5 years Python" in cleaned


def test_chunks_to_dicts_and_back_roundtrip():
    chunks = chunk_resume("Experience\n• Built a thing")
    restored = chunks_from_dicts(chunks_to_dicts(chunks))
    assert restored == chunks
