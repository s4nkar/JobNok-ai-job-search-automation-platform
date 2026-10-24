"""Unit tests for resume_tailor.validation — deterministic anti-hallucination
checks on LLM-generated bullet rewrites, no I/O, no mocking needed."""

from app.modules.resume_tailor.validation import (
    validate_bullet_patch,
    validate_headline_skills,
    validate_llm_jd_chunks,
    validate_llm_resume_chunks,
    validate_summary,
)


def test_validate_bullet_patch_accepts_when_numbers_preserved():
    resume = "Led a project that increased revenue by 40% using Python and AWS."
    improved = "Spearheaded a project that grew revenue by 40% leveraging Python and AWS."
    result = validate_bullet_patch("b0", improved, resume)
    assert result.ok is True
    assert result.violations == []


def test_validate_bullet_patch_rejects_fabricated_metric():
    resume = "Led a project that increased revenue using Python."
    improved = "Led a project that increased revenue by 75% using Python."
    result = validate_bullet_patch("b0", improved, resume)
    assert result.ok is False
    assert any("75" in v for v in result.violations)


def test_validate_bullet_patch_rejects_fabricated_tool_name():
    resume = "Built data pipelines using Python."
    improved = "Built data pipelines using Python and Kubernetes."
    result = validate_bullet_patch("b0", improved, resume)
    assert result.ok is False
    assert any("Kubernetes" in v for v in result.violations)


def test_validate_bullet_patch_accepts_reworded_verb_with_same_evidence():
    resume = "Built data pipelines using Python for the analytics team."
    improved = "Engineered data pipelines using Python for the analytics team."
    result = validate_bullet_patch("b0", improved, resume)
    assert result.ok is True


def test_validate_bullet_patch_accepts_number_relocated_from_elsewhere_in_resume():
    resume = "Managed a team. Elsewhere in the resume: increased throughput by 40% via caching."
    improved = "Managed a team, increased throughput by 40%."
    result = validate_bullet_patch("b0", improved, resume)
    assert result.ok is True


def test_validate_bullet_patch_ignores_case_differences():
    resume = "Built ML models using PyTorch for production inference."
    improved = "Built ML models using Pytorch for production inference."
    result = validate_bullet_patch("b0", improved, resume)
    assert result.ok is True


def test_validate_headline_skills_ignores_title_segment():
    resume = "Built services using Python."
    headline = "Senior Platform Engineer | Python"
    result = validate_headline_skills(headline, resume)
    assert result.ok is True


def test_validate_headline_skills_rejects_fabricated_skill():
    resume = "Built services using Python."
    headline = "Senior Platform Engineer | Python | Kubernetes"
    result = validate_headline_skills(headline, resume)
    assert result.ok is False
    assert any("Kubernetes" in v for v in result.violations)


def test_validate_summary_skips_number_check_for_computed_years():
    resume = "Software engineer who worked at Acme from 2021 to 2024 building backend systems in Python."
    summary = "Software Engineer with 3+ years of experience building backend systems in Python."
    result = validate_summary(summary, resume)
    assert result.ok is True


def test_validate_summary_rejects_missing_keyword_skill():
    resume = "Software engineer building backend systems in Python."
    summary = "Software Engineer experienced in Python and Kubernetes."
    result = validate_summary(summary, resume)
    assert result.ok is False


# ── validate_llm_jd_chunks ────────────────────────────────────────────

_JD_TEXT = (
    "Requirements:\n"
    "5+ years of Python experience building production backend services.\n"
    "Strong understanding of distributed systems and REST API design.\n"
    "Experience with PostgreSQL and Redis in a production environment."
)


def test_validate_llm_jd_chunks_accepts_verbatim_chunks():
    raw = [
        {"kind": "requirement", "text": "5+ years of Python experience building production backend services."},
        {"kind": "requirement", "text": "Strong understanding of distributed systems and REST API design."},
        {"kind": "requirement", "text": "Experience with PostgreSQL and Redis in a production environment."},
    ]
    chunks = validate_llm_jd_chunks(raw, _JD_TEXT)
    assert chunks is not None
    assert [c.text for c in chunks] == [r["text"] for r in raw]
    assert all(c.kind == "requirement" and c.section == "requirements" for c in chunks)


def test_validate_llm_jd_chunks_drops_invented_chunk_not_in_source():
    # A short, SELF-CONTAINED source (not the shared _JD_TEXT) so the one
    # genuine chunk alone clears the 50% coverage floor — _JD_TEXT has three
    # requirement lines, and offering only one of them against that larger
    # source would (correctly) fail the coverage check for an unrelated
    # reason, masking the thing this test actually checks.
    source = "5+ years of Python experience building production backend services."
    raw = [
        {"kind": "requirement", "text": source},
        # Not in the source text at all — a hallucinated/invented chunk.
        {"kind": "requirement", "text": "Must be willing to relocate to Mars within 30 days."},
    ]
    chunks = validate_llm_jd_chunks(raw, source)
    assert chunks is not None
    assert len(chunks) == 1
    assert "Mars" not in chunks[0].text


def test_validate_llm_jd_chunks_drops_unrecognised_kind():
    raw = [{"kind": "not_a_real_kind", "text": "5+ years of Python experience building production backend services."}]
    # Only chunk offered has an invalid kind, and on its own it's below the
    # coverage floor once dropped -> whole attempt rejected.
    assert validate_llm_jd_chunks(raw, _JD_TEXT) is None


def test_validate_llm_jd_chunks_rejects_when_coverage_too_low():
    # Every chunk is paraphrased (not a verbatim substring) -> nothing survives
    # the verbatim check -> coverage is ~0% -> whole attempt rejected, caller
    # falls back to the regex chunker.
    raw = [{"kind": "requirement", "text": "Needs solid Python skills for backend work."}]
    assert validate_llm_jd_chunks(raw, _JD_TEXT) is None


def test_validate_llm_jd_chunks_rejects_empty_or_non_list_input():
    assert validate_llm_jd_chunks([], _JD_TEXT) is None
    assert validate_llm_jd_chunks(None, _JD_TEXT) is None  # type: ignore[arg-type]


def test_validate_llm_jd_chunks_orders_by_source_position():
    # Offered out of order — kept chunks must come back in SOURCE order, not
    # the order the LLM happened to emit them in (matcher.py assumes document
    # order is preserved from the regex chunker and nothing downstream
    # re-sorts).
    raw = [
        {"kind": "requirement", "text": "Experience with PostgreSQL and Redis in a production environment."},
        {"kind": "requirement", "text": "5+ years of Python experience building production backend services."},
    ]
    chunks = validate_llm_jd_chunks(raw, _JD_TEXT)
    assert chunks is not None
    assert chunks[0].text.startswith("5+ years")
    assert chunks[1].text.startswith("Experience with PostgreSQL")


# ── validate_llm_resume_chunks ────────────────────────────────────────

_RESUME_TEXT = (
    "PROFESSIONAL SUMMARY\n"
    "Applied AI Engineer with hands-on experience building production AI systems.\n"
    "PROFESSIONAL EXPERIENCE\n"
    "Applied AI Engineer - JobNok 2025 - Present\n"
    "Architected an asynchronous agentic pipeline using FastAPI, Redis, and ARQ.\n"
    "TECHNICAL SKILLS\n"
    "PyTorch, TensorFlow"
)


def test_validate_llm_resume_chunks_accepts_verbatim_chunks():
    raw = [
        {"kind": "summary", "section": "summary", "text": "Applied AI Engineer with hands-on experience building production AI systems."},
        {"kind": "header", "section": "header", "text": "Applied AI Engineer - JobNok 2025 - Present"},
        {"kind": "bullet", "section": "experience", "text": "Architected an asynchronous agentic pipeline using FastAPI, Redis, and ARQ."},
        {"kind": "skill", "section": "skills", "text": "PyTorch"},
        {"kind": "skill", "section": "skills", "text": "TensorFlow"},
    ]
    chunks = validate_llm_resume_chunks(raw, _RESUME_TEXT)
    assert chunks is not None
    assert [c.text for c in chunks] == [r["text"] for r in raw]
    assert [c.kind for c in chunks] == ["summary", "header", "bullet", "skill", "skill"]


def test_validate_llm_resume_chunks_drops_hallucinated_bullet():
    # Self-contained source (not the shared _RESUME_TEXT, which has several
    # other lines the single offered real chunk wouldn't cover 50% of).
    source = "Architected an asynchronous agentic pipeline using FastAPI, Redis, and ARQ."
    raw = [
        {"kind": "bullet", "section": "experience", "text": source},
        # Not present anywhere in the source resume.
        {"kind": "bullet", "section": "experience", "text": "Led a team of 50 engineers to a successful IPO."},
    ]
    chunks = validate_llm_resume_chunks(raw, source)
    assert chunks is not None
    assert len(chunks) == 1
    assert "IPO" not in chunks[0].text


def test_validate_llm_resume_chunks_drops_unrecognised_section():
    source = "Architected an asynchronous agentic pipeline using FastAPI, Redis, and ARQ."
    raw = [
        {"kind": "bullet", "section": "experience", "text": source},
        # "made_up_section" isn't in the fixed section vocabulary — dropped,
        # not trusted verbatim, even though the text itself is real.
        {"kind": "bullet", "section": "made_up_section", "text": "PyTorch, TensorFlow"},
    ]
    chunks = validate_llm_resume_chunks(raw, source)
    assert chunks is not None
    assert all(c.section != "made_up_section" for c in chunks)


def test_validate_llm_resume_chunks_drops_unrecognised_kind():
    raw = [{"kind": "requirement", "section": "experience", "text": "Architected an asynchronous agentic pipeline using FastAPI, Redis, and ARQ."}]
    # "requirement" is a JD-side kind, not a valid resume-chunk kind — on its
    # own, dropping it takes coverage to 0 -> whole attempt rejected.
    assert validate_llm_resume_chunks(raw, _RESUME_TEXT) is None


def test_validate_llm_resume_chunks_rejects_when_coverage_too_low():
    raw = [{"kind": "bullet", "section": "experience", "text": "Built an async pipeline with FastAPI."}]
    assert validate_llm_resume_chunks(raw, _RESUME_TEXT) is None
