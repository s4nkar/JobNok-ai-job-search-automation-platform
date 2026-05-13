"""Deterministic resume↔JD matching, scoring, and gap analysis.

This module is the architectural heart of the tailoring pipeline. Given chunked
resume + JD content and their embeddings, it produces a structured analysis
WITHOUT any LLM call:

  - per-requirement evidence linkage
  - matched / missing ATS keywords (exact)
  - score breakdown by category (skills, responsibilities, domain, ATS)
  - gap classification (critical / transferable)
  - shortlist of resume bullets that are good candidates for LLM rewrite
    (i.e. transferable but not strongly aligned with the JD requirement)

The LLM is invoked downstream with these structured results as context, so its
job shrinks from "do the whole analysis" to "generate prose for headline,
summary, and a handful of bullet rewrites." This is cheaper, faster, and avoids
the recurring failure mode where a single giant prompt hallucinates evidence or
fabricates skills.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from lib.resume_chunker import Chunk

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────
# Tuned for Jina v3 / Cohere embed-v3 cosine scores. If you switch models, these
# may need adjustment.
STRONG_THRESHOLD = 0.72
PARTIAL_THRESHOLD = 0.55
# Bullets in this band are best candidates for AI rewrite — meaningful overlap,
# but framing could be sharpened.
REWRITE_BAND = (0.50, 0.78)
MAX_REWRITE_BULLETS = 5

# Category weights — match the architecture doc's example scoring shape.
SCORE_WEIGHTS = {
    "core_skills": 0.30,
    "responsibilities": 0.25,
    "domain": 0.15,
    "ats_keywords": 0.20,
    "seniority": 0.10,
}

MatchType = Literal["strong", "partial", "missing"]


# ── Data shapes ───────────────────────────────────────────────────

@dataclass
class RequirementMatch:
    requirement: str
    requirement_kind: str  # JD chunk kind: requirement | responsibility | domain
    best_evidence: str | None
    best_evidence_section: str | None
    score: float
    match_type: MatchType

    def as_dict(self) -> dict:
        return {
            "requirement": self.requirement,
            "requirement_kind": self.requirement_kind,
            "best_evidence": self.best_evidence,
            "best_evidence_section": self.best_evidence_section,
            "score": round(self.score, 3),
            "match_type": self.match_type,
        }


@dataclass
class RewriteCandidate:
    resume_bullet: str
    target_requirement: str
    similarity: float

    def as_dict(self) -> dict:
        return {
            "original": self.resume_bullet,
            "target_requirement": self.target_requirement,
            "similarity": round(self.similarity, 3),
        }


@dataclass
class MatchResult:
    matches: list[RequirementMatch] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    transferable_strengths: list[str] = field(default_factory=list)
    critical_missing: list[str] = field(default_factory=list)
    rewrite_candidates: list[RewriteCandidate] = field(default_factory=list)
    score_breakdown: dict[str, int] = field(default_factory=dict)
    overall_score: int = 0
    degraded: bool = False  # True when embeddings failed and we used keywords only

    def as_dict(self) -> dict:
        return {
            "matches": [m.as_dict() for m in self.matches],
            "matched_keywords": self.matched_keywords,
            "missing_keywords": self.missing_keywords,
            "transferable_strengths": self.transferable_strengths,
            "critical_missing": self.critical_missing,
            "rewrite_candidates": [r.as_dict() for r in self.rewrite_candidates],
            "score_breakdown": self.score_breakdown,
            "overall_score": self.overall_score,
            "degraded": self.degraded,
        }


# ── Keyword extraction (deterministic, no AI) ─────────────────────

# Match likely technical tokens:
#   - acronyms (2+ uppercase chars):  AWS, GCP, SQL, ML, NLP, API
#   - CamelCase / PascalCase:         PyTorch, TensorFlow, JavaScript, FastAPI
#   - dotted/hyphenated tech:         .NET, CI/CD, Node.js, C++
#   - multi-word phrases (curated):   machine learning, computer vision
_TOKEN_RE = re.compile(
    r"""
    \b(
        [A-Z][A-Za-z0-9]*(?:[+\-./][A-Za-z0-9]+)+     # C++, CI/CD, Node.js
        | [A-Z]{2,}(?:[0-9]+)?                         # AWS, GCP, S3, ML
        | [A-Z][a-z]+[A-Z][A-Za-z0-9]*                 # PyTorch, FastAPI
        | [A-Z][a-z]{2,}                               # Python, Docker (single-cap is allowed)
    )\b
    """,
    re.VERBOSE,
)

# Multi-word tech phrases that won't survive single-token extraction.
_PHRASES = [
    "machine learning", "deep learning", "computer vision", "natural language processing",
    "reinforcement learning", "data engineering", "data science", "data pipelines",
    "feature engineering", "model deployment", "model serving", "real time",
    "large language model", "vector database", "prompt engineering",
    "cloud infrastructure", "distributed systems", "system design",
    "test driven development", "continuous integration", "continuous deployment",
    "design patterns",
    # Tools / platforms that read as two tokens individually
    "weights and biases", "weights & biases",
    "amazon web services", "aws",
    "data pipeline", "data pipelines",
    "google cloud platform",
    "high performance computing",
    "remote sensing",
    "satellite imagery",
    "change detection",
    "time series",
    "object detection",
]

# Common false-positive tokens that match the regex but aren't useful keywords.
# Rule: a word belongs here if it (a) isn't a technology/skill name, and
# (b) commonly appears capitalised in JD prose (sentence-initial verbs,
# location names, company metadata, generic adjectives).
_KEYWORD_STOPWORDS = {
    # Pronouns / determiners / conjunctions
    "The", "This", "That", "These", "Those", "With", "From", "Into",
    "Will", "What", "When", "Where", "Which", "Who", "Why", "How",
    "Your", "Our", "Their", "His", "Her", "Its", "And", "But", "Not",
    "You", "We", "For", "Are", "Can", "May", "Must", "Has", "Have",
    # Generic JD section labels
    "Resume", "JD", "Job", "Role", "Team", "Company", "Description",
    "Overview", "Requirements", "Responsibilities", "Benefits", "Opportunity",
    "Location", "About", "Founded", "Join", "Ownership",
    # Common sentence-initial verbs that are NOT skills
    "Build", "Develop", "Apply", "Contribute", "Improve", "Support",
    "Collaborate", "Communicate", "Deliver", "Create", "Design", "Define",
    "Translate", "Provide", "Enable", "Leverage", "Utilize", "Ensure",
    "Manage", "Lead", "Drive", "Grow", "Learn", "Use", "Run", "Help",
    "Feeling", "Hands-on",
    # Generic adjectives / adverbs in JD prose
    "Nice", "Modern", "Flexible", "Competitive", "Strong", "Clear",
    "Understanding", "Familiarity", "Direct", "Through",
    # Location / company names that leak in via capitalised tokens
    "Munich", "München", "Mannheim", "Deutschland", "Sendlinger", "Tor",
    "Goldman", "Sachs", "Decarbonization", "Partners",
    # Company-specific product / programme names (not transferable skills)
    "HUB",
    # Solo tokens that are subsumed by a multi-word phrase already in _PHRASES
    # (e.g. "Weights" and "Biases" are noise when "weights & biases" is captured)
    "Weights", "Biases",
    # Generic standalone words that add no signal without their partner token
    "Services", "Web",
    # Business model / product descriptors (not candidate skills)
    "Software-as-a-Service",
    # Tracker-appended metadata words
    "Matched", "Paste", "Signal", "Signals",
    # Funding / company stage metadata
    "Stage", "Series", "Seed",
    # JD personality / culture words (not technical skills)
    "Adaptability", "Pace", "Positive", "Ownership",
    # Sentence-initial verbs common in startup JDs
    "Architect", "Challenge", "Decide", "Enjoy", "Fine-tune", "Keep",
    "Set", "Shape",
    # Benefits section noise
    "Club", "Free", "Sports", "Urban",
    # Generic labels that appear as tokens
    "Development", "Engineering", "Expertise", "Qualifications", "Language",
    "Tech-Leverage", "Berlin/Leipzig",
    # Company names that appear as keywords
    "Circula",
    # Solo tokens subsumed by phrases or too generic alone
    "System",  # "system design" is the phrase; "System" alone adds no signal
    "Cloud",   # "cloud infrastructure" is the phrase
    # Months (appear in date ranges inside JDs)
    "January", "February", "March", "April", "June", "July", "August",
    "September", "October", "November", "December",
}


def extract_keywords(text: str) -> set[str]:
    """Return a set of likely technical keywords from arbitrary text.

    Output is the original token casing (e.g. "PyTorch", not "pytorch"). For
    matching, callers should casefold both sides.
    """
    tokens = {m.group(1) for m in _TOKEN_RE.finditer(text)}
    tokens = {t for t in tokens if t not in _KEYWORD_STOPWORDS and len(t) >= 2}

    lower = text.lower()
    for phrase in _PHRASES:
        if phrase in lower:
            tokens.add(phrase)

    return tokens


def _casefold_set(items: set[str]) -> dict[str, str]:
    """Map casefolded form → original display form. Last-write wins on collisions."""
    return {it.casefold(): it for it in items}


# ── Core matching ─────────────────────────────────────────────────

def match_resume_to_jd(
    resume_chunks: list[Chunk],
    resume_embeddings: "np.ndarray",
    jd_chunks: list[Chunk],
    jd_embeddings: "np.ndarray",
    resume_text: str,
    jd_text: str,
) -> MatchResult:
    """Run the full deterministic match. resume_text/jd_text are used for keyword
    extraction in addition to chunked content.

    If embeddings are missing or shape-mismatched we fall back to keyword-only
    matching with degraded=True. The caller can still produce a useful (if
    less nuanced) report rather than failing the whole request.
    """
    from lib.embeddings import similarity_matrix

    result = MatchResult()

    # Keyword layer — always runs, independent of embeddings.
    resume_kw = extract_keywords(resume_text)
    jd_kw = extract_keywords(jd_text)
    r_lower = _casefold_set(resume_kw)
    j_lower = _casefold_set(jd_kw)

    matched_lower = set(r_lower) & set(j_lower)
    missing_lower = set(j_lower) - set(r_lower)
    # Display using JD's casing (it's what the candidate needs to mirror).
    result.matched_keywords = sorted({j_lower[k] for k in matched_lower}, key=str.lower)
    result.missing_keywords = sorted({j_lower[k] for k in missing_lower}, key=str.lower)

    # Embedding-driven match layer.
    can_embed = (
        resume_embeddings.size > 0
        and jd_embeddings.size > 0
        and resume_embeddings.shape[0] == len(resume_chunks)
        and jd_embeddings.shape[0] == len(jd_chunks)
    )
    if not can_embed:
        result.degraded = True
        _populate_keyword_only_scores(result, jd_kw)
        return result

    # (n_resume, n_jd) similarity matrix.
    S = similarity_matrix(resume_embeddings, jd_embeddings)

    for j_idx, jd_chunk in enumerate(jd_chunks):
        col = S[:, j_idx]
        best_idx = int(col.argmax()) if col.size else -1
        best_score = float(col[best_idx]) if best_idx >= 0 else 0.0

        if best_score >= STRONG_THRESHOLD:
            match_type: MatchType = "strong"
        elif best_score >= PARTIAL_THRESHOLD:
            match_type = "partial"
        else:
            match_type = "missing"

        result.matches.append(RequirementMatch(
            requirement=jd_chunk.text,
            requirement_kind=jd_chunk.kind,
            best_evidence=resume_chunks[best_idx].text if best_idx >= 0 and match_type != "missing" else None,
            best_evidence_section=resume_chunks[best_idx].section if best_idx >= 0 and match_type != "missing" else None,
            score=best_score,
            match_type=match_type,
        ))

    # Transferable strengths = partial matches against requirement-kind JD chunks.
    # These are the bullets to surface in the report as "you have related but not
    # explicit experience here."
    transferable = [m for m in result.matches if m.match_type == "partial" and m.requirement_kind == "requirement"]
    result.transferable_strengths = [t.requirement for t in transferable[:8]]

    # Critical missing = requirement-kind JD chunks with NO partial/strong match
    # AND no keyword overlap. Hard gaps the candidate shouldn't try to fake.
    critical: list[str] = []
    for m in result.matches:
        if m.match_type != "missing" or m.requirement_kind != "requirement":
            continue
        # If a keyword for this requirement IS in the resume, it's not truly missing.
        req_kw = extract_keywords(m.requirement)
        if req_kw and any(k.casefold() in r_lower for k in req_kw):
            continue
        critical.append(m.requirement)
    result.critical_missing = critical[:10]

    # Rewrite candidates: resume bullets that landed in the partial band against
    # a requirement-kind JD chunk. Sharpening the framing of these bullets is the
    # highest-value AI rewrite work.
    rewrite_pool: list[RewriteCandidate] = []
    seen_bullets: set[str] = set()
    for j_idx, jd_chunk in enumerate(jd_chunks):
        if jd_chunk.kind != "requirement":
            continue
        col = S[:, j_idx]
        # Walk resume chunks in descending order of similarity.
        order = col.argsort()[::-1]
        for i_idx in order[:3]:
            r_chunk = resume_chunks[int(i_idx)]
            if r_chunk.kind != "bullet":
                continue
            # Education, publication, and header entries aren't rewritable bullets.
            if r_chunk.section in ("education", "header", "publications", "certifications", "languages"):
                continue
            sim = float(col[int(i_idx)])
            if not (REWRITE_BAND[0] <= sim <= REWRITE_BAND[1]):
                continue
            if r_chunk.text in seen_bullets:
                continue
            seen_bullets.add(r_chunk.text)
            rewrite_pool.append(RewriteCandidate(
                resume_bullet=r_chunk.text,
                target_requirement=jd_chunk.text,
                similarity=sim,
            ))
    # Sort by similarity descending — best candidates first — then cap.
    rewrite_pool.sort(key=lambda r: r.similarity, reverse=True)
    result.rewrite_candidates = rewrite_pool[:MAX_REWRITE_BULLETS]

    # Score breakdown.
    result.score_breakdown = _compute_score_breakdown(result.matches, len(jd_kw), len(matched_lower))
    result.overall_score = _weighted_overall(result.score_breakdown)

    return result


def _populate_keyword_only_scores(result: MatchResult, jd_kw: set[str]) -> None:
    """Fallback scoring when embeddings are unavailable. Uses only keyword overlap."""
    if not jd_kw:
        result.score_breakdown = {k: 0 for k in SCORE_WEIGHTS}
        result.overall_score = 0
        return
    kw_pct = int(round(100 * len(result.matched_keywords) / max(1, len(jd_kw))))
    # Without embeddings we can't differentiate categories — apply kw_pct uniformly
    # and flag degraded so the UI can warn the user.
    result.score_breakdown = {k: kw_pct for k in SCORE_WEIGHTS}
    result.overall_score = kw_pct


def _compute_score_breakdown(
    matches: list[RequirementMatch],
    jd_keyword_count: int,
    matched_keyword_count: int,
) -> dict[str, int]:
    """Convert per-requirement match scores into category-level 0-100 scores."""
    def avg_score_for_kind(kind: str) -> int:
        scored = [m.score for m in matches if m.requirement_kind == kind]
        if not scored:
            return 0
        # Scale cosine [0, 1] → [0, 100] with a floor at 0.
        return int(round(100 * max(0.0, sum(scored) / len(scored))))

    ats_pct = int(round(100 * matched_keyword_count / max(1, jd_keyword_count))) if jd_keyword_count else 0

    req_score = avg_score_for_kind("requirement")
    resp_score = avg_score_for_kind("responsibility")
    return {
        "core_skills": req_score,
        # Many JDs (especially startup ones) have no explicit "Responsibilities"
        # section — all bullets are requirements. Fall back to req_score so the
        # category doesn't misleadingly show 0.
        "responsibilities": resp_score if resp_score > 0 else req_score,
        "domain": avg_score_for_kind("domain"),
        "ats_keywords": ats_pct,
        "seniority": req_score,
    }


def _weighted_overall(breakdown: dict[str, int]) -> int:
    total = 0.0
    for key, weight in SCORE_WEIGHTS.items():
        total += breakdown.get(key, 0) * weight
    return int(round(total))
