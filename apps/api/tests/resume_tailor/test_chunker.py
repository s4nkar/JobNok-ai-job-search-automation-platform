"""Unit tests for resume_tailor.chunker — pure regex/heuristic functions,
no I/O, no mocking needed."""

from app.modules.resume_tailor.chunker import (
    Chunk,
    chunk_jd,
    chunk_resume,
    chunks_from_dicts,
    chunks_to_dicts,
    clean_jd_text,
    jd_chunking_is_pathological,
    resume_chunking_is_pathological,
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
    # Long enough that the cleaned result clears _JD_MIN_USEFUL_LEN (120 chars)
    # on its own — clean_jd_text falls back to the ORIGINAL uncleaned text
    # whenever the cleaned result looks implausibly short (a deliberate guard
    # against a mis-fire gutting a real JD), which a short synthetic fixture
    # trips for the wrong reason and defeats the thing this test checks.
    text = (
        "Requirements:\n"
        "- 5+ years of Python experience building production backend services\n"
        "- Strong understanding of distributed systems and REST API design\n"
        "- Experience with PostgreSQL and Redis in a production environment\n"
        "Role Signals:\n"
        "• Matched Role Keywords: Python, SQL"
    )
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


# ── jd_chunking_is_pathological / resume_chunking_is_pathological ────────
# Both delegate to the same shared _chunking_is_pathological heuristic, just
# with a different "signal kind" set — tested once per public entry point
# since each has its own real callers (generation.py's two *_with_llm_repair
# functions) and its own kind vocabulary (requirement/responsibility vs
# bullet/skill).

def test_jd_chunking_is_pathological_skipped_for_short_text():
    # Below _PATHOLOGICAL_MIN_TEXT_LEN (400 chars) — too little text for the
    # share checks to be a meaningful signal rather than noise, regardless of
    # how bad the chunks look.
    short_text = "Short JD."
    chunks = [Chunk(kind="domain", section="about", text=short_text)]
    assert jd_chunking_is_pathological(chunks, short_text) is False


def test_jd_chunking_is_pathological_true_when_requirement_share_too_low():
    text = "Company blurb. " * 40  # 640 chars, well past the 400-char floor
    chunks = [
        Chunk(kind="domain", section="about", text=text),
        # A token amount of real requirement content — nowhere near the
        # share a real posting would spend on actual asks.
        Chunk(kind="requirement", section="requirements", text="Python required."),
    ]
    assert jd_chunking_is_pathological(chunks, text) is True


def test_jd_chunking_is_pathological_true_when_one_chunk_dominates():
    # A single oversized chunk holding most of the text — the "line-splitting
    # logic failed to break up a run-on block" tell, independent of kind
    # mix (this chunk IS correctly kind="requirement", it's just unsplit).
    blob = "Requires Python, SQL, AWS, Docker, Kubernetes experience. " * 10  # ~600 chars
    chunks = [Chunk(kind="requirement", section="requirements", text=blob)]
    assert jd_chunking_is_pathological(chunks, blob) is True


def test_jd_chunking_is_pathological_false_for_healthy_distribution():
    reqs = [f"Requirement number {i} about a specific tool or skill in detail." for i in range(10)]
    text = " ".join(reqs)
    chunks = [Chunk(kind="requirement", section="requirements", text=r) for r in reqs]
    assert jd_chunking_is_pathological(chunks, text) is False


def test_resume_chunking_is_pathological_true_when_bullet_skill_share_too_low():
    text = "Header metadata line. " * 40  # well past the 400-char floor
    chunks = [
        Chunk(kind="header", section="header", text=text),
        Chunk(kind="bullet", section="experience", text="Built a thing."),
    ]
    assert resume_chunking_is_pathological(chunks, text) is True


def test_resume_chunking_is_pathological_false_for_healthy_distribution():
    bullets = [f"Built and shipped feature number {i} for production users at scale." for i in range(10)]
    text = " ".join(bullets)
    chunks = [Chunk(kind="bullet", section="experience", text=b) for b in bullets]
    assert resume_chunking_is_pathological(chunks, text) is False
