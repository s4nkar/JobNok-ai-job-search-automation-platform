"""Unit tests for resume_tailor.matcher — deterministic similarity-matrix +
keyword-overlap matching, no I/O, no mocking needed. Embeddings are supplied
as hand-crafted numpy arrays with known dot-product values rather than real
vectors — match_resume_to_jd/similarity_matrix trust the caller's vectors are
already normalized and just take a raw dot product, so an exact value can be
engineered directly without needing genuinely unit-normalized vectors.
"""

import numpy as np

from app.modules.resume_tailor.chunker import Chunk
from app.modules.resume_tailor.matcher import (
    MAX_REWRITE_BULLETS,
    extract_keywords,
    match_resume_to_jd,
)

_EMPTY = np.zeros((0, 0), dtype="float32")


def test_extract_keywords_exact_match():
    kws = extract_keywords("Experience with Python and Docker")
    assert "Python" in kws
    assert "Docker" in kws


def test_extract_keywords_case_insensitive_matching_via_casefold():
    resume_kw = {k.casefold() for k in extract_keywords("Skilled in PYTHON development")}
    jd_kw = {k.casefold() for k in extract_keywords("Requires Python expertise")}
    assert "python" in resume_kw
    assert "python" in jd_kw


def test_extract_keywords_pluralization_alias():
    kws = extract_keywords("We use data pipelines extensively")
    assert "data pipeline" in kws
    assert "data pipelines" not in kws


def test_extract_keywords_duplicate_keywords_deduplicated():
    kws = extract_keywords("Python Python Python")
    assert list(kws).count("Python") == 1


def test_extract_keywords_filters_stopwords():
    kws = extract_keywords("The Team will Build Strong products")
    for stopword in ("The", "Team", "Build", "Strong"):
        assert stopword not in kws


def test_match_resume_to_jd_missing_skills_reported():
    resume_chunks = [Chunk(kind="skill", section="skills", text="Python")]
    jd_chunks = [Chunk(kind="requirement", section="requirements", text="Requires Python and Kubernetes")]
    result = match_resume_to_jd(
        resume_chunks=resume_chunks, resume_embeddings=_EMPTY,
        jd_chunks=jd_chunks, jd_embeddings=_EMPTY,
        resume_text="Python", jd_text="Requires Python and Kubernetes",
    )
    assert "Kubernetes" in result.missing_keywords
    assert "Python" in result.matched_keywords


def test_match_resume_to_jd_empty_jd_returns_zero_score():
    result = match_resume_to_jd(
        resume_chunks=[Chunk(kind="skill", section="skills", text="Python")],
        resume_embeddings=_EMPTY,
        jd_chunks=[], jd_embeddings=_EMPTY,
        resume_text="Python", jd_text="",
    )
    assert result.overall_score == 0


def test_match_resume_to_jd_empty_resume_degrades_gracefully():
    result = match_resume_to_jd(
        resume_chunks=[], resume_embeddings=_EMPTY,
        jd_chunks=[Chunk(kind="requirement", section="requirements", text="Requires Python")],
        jd_embeddings=_EMPTY,
        resume_text="", jd_text="Requires Python",
    )
    assert result.degraded is True
    assert "Python" in result.missing_keywords


def test_match_resume_to_jd_degraded_when_embeddings_shape_mismatched():
    resume_chunks = [
        Chunk(kind="skill", section="skills", text="Python"),
        Chunk(kind="skill", section="skills", text="SQL"),
    ]
    jd_chunks = [Chunk(kind="requirement", section="requirements", text="Requires Python")]
    result = match_resume_to_jd(
        resume_chunks=resume_chunks, resume_embeddings=np.zeros((1, 8), dtype="float32"),
        jd_chunks=jd_chunks, jd_embeddings=np.zeros((1, 8), dtype="float32"),
        resume_text="Python SQL", jd_text="Requires Python",
    )
    assert result.degraded is True


def test_match_resume_to_jd_non_english_text_documents_current_ascii_limitation():
    """matcher.py has no language awareness — extract_keywords() is a plain
    ASCII-letter regex with no translation/language filtering (that lives
    upstream in generation.py's _is_english/_translate_jd). Non-English
    structural words simply pass through as if they were skills; this test
    documents that as a known limitation of the deterministic layer, not a
    behavior to assert as correct."""
    kws = extract_keywords("Erfahrung mit Python und Kubernetes")
    assert "Python" in kws
    assert "Kubernetes" in kws
    assert "Erfahrung" in kws


def test_rewrite_candidates_capped_at_max_rewrite_bullets():
    jd_chunks = [
        Chunk(kind="requirement", section="requirements", text="Requires strong backend engineering"),
        Chunk(kind="requirement", section="requirements", text="Requires distributed systems experience"),
    ]
    jd_embeddings = np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32")

    resume_chunks = [
        Chunk(kind="bullet", section="experience", text=f"Built backend service number {i} for production traffic")
        for i in range(3)
    ] + [
        Chunk(kind="bullet", section="experience", text=f"Designed distributed system component number {i} at scale")
        for i in range(3)
    ]
    resume_embeddings = np.array([[0.65, 0.1]] * 3 + [[0.1, 0.65]] * 3, dtype="float32")

    result = match_resume_to_jd(
        resume_chunks=resume_chunks, resume_embeddings=resume_embeddings,
        jd_chunks=jd_chunks, jd_embeddings=jd_embeddings,
        resume_text=" ".join(c.text for c in resume_chunks),
        jd_text=" ".join(c.text for c in jd_chunks),
    )
    assert len(result.rewrite_candidates) == MAX_REWRITE_BULLETS


def test_rewrite_candidates_excludes_education_and_header_sections():
    jd_chunks = [Chunk(kind="requirement", section="requirements", text="Requires strong backend engineering")]
    jd_embeddings = np.array([[1.0]], dtype="float32")

    resume_chunks = [
        Chunk(kind="bullet", section="education", text="Studied backend engineering fundamentals at university"),
        Chunk(kind="bullet", section="experience", text="Built backend services for production traffic daily"),
    ]
    resume_embeddings = np.array([[0.65], [0.65]], dtype="float32")

    result = match_resume_to_jd(
        resume_chunks=resume_chunks, resume_embeddings=resume_embeddings,
        jd_chunks=jd_chunks, jd_embeddings=jd_embeddings,
        resume_text=" ".join(c.text for c in resume_chunks), jd_text=jd_chunks[0].text,
    )
    assert len(result.rewrite_candidates) == 1
    assert result.rewrite_candidates[0].resume_bullet == "Built backend services for production traffic daily"
