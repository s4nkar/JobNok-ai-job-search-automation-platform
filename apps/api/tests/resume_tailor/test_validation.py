"""Unit tests for resume_tailor.validation — deterministic anti-hallucination
checks on LLM-generated bullet rewrites, no I/O, no mocking needed."""

from app.modules.resume_tailor.validation import validate_bullet_patch, validate_headline_skills, validate_summary


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
    assert any("Kubernetes" in v for v in result.violations)
