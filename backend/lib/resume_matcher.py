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
    "predictive analytics", "predictive modeling",
    "model deployment", "model serving",
    "etl pipeline", "etl process",
    "chatbot",
    "google cloud platform",
    "high performance computing",
    "remote sensing",
    "satellite imagery",
    "change detection",
    "time series",
    "object detection",
    # Recommender system domain
    "recommender system", "recommender systems", "collaborative filtering",
    "content-based filtering", "content based filtering",
    "matrix factorization", "knowledge graph",
    # MLOps / evaluation
    "a/b testing", "evaluation framework", "model evaluation",
    "data versioning", "model registry",
    # Agentic / LLM tooling
    "agentic pipeline", "agentic pipelines", "mcp server",
    "multi-agent", "function calling",
]

# Canonical form for plural/variant phrases — keyed by the non-canonical form.
# If a text contains the key, it's replaced by the value before comparison so
# "data pipelines" and "data pipeline" are treated as the same keyword.
_PHRASE_ALIASES: dict[str, str] = {
    "data pipelines": "data pipeline",
    "etl processes": "etl process",
    "etl pipelines": "etl pipeline",
    "predictive models": "predictive modeling",
    "large language models": "large language model",
    "vector databases": "vector database",
    "recommender systems": "recommender system",
    "agentic pipelines": "agentic pipeline",
    "mcp servers": "mcp server",
}

# Token → canonical phrase. Applied after stopword filtering so a bare acronym
# token is collapsed into its phrase form — prevents ETL / etl process duplicates
# when both the acronym and its full phrase appear in the same text.
_TOKEN_ALIASES: dict[str, str] = {
    "ETL": "etl process",
    "Chatbots": "chatbot",  # plural token → singular canonical form
}

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
    # Additional sentence-initial verbs common in modern JD phrasing
    "Bring", "Operate", "Prototype", "Synthesize", "Iterate", "Identify",
    "Optimize", "Transform", "Influence", "Raise", "Serving", "Turning",
    "Balancing", "Debugging", "Iterating", "Prototyping", "Partner",
    "Thrive", "Combining", "Shaping", "Shipping", "Working",
    # Generic adjectives / adverbs in JD prose
    "Nice", "Modern", "Flexible", "Competitive", "Strong", "Clear",
    "Understanding", "Familiarity", "Direct", "Through",
    # Qualifier adjectives that prefix real skills but aren't skills themselves
    "Excellent", "Foundational", "Minimum", "Solid", "Profound", "Fluent",
    "Structured", "Several", "Proficient", "Diverse", "Individual", "Various",
    "Above-average", "Team-oriented", "Solution-oriented", "In-depth",
    "Comprehensive", "Careful", "Provable",
    # "Frameworks" alone is too generic — the actual framework name is the signal
    "Frameworks",
    # Hyphenated compound variants already covered by the base token
    "Tensorflow-based", "Docker-based",
    # Benefits / perks product names that survive translation
    "Hansefit", "Quooker",
    # Contact / apply section noise
    "Please", "Contact", "Because", "Mobility",
    # Location / company names that leak in via capitalised tokens
    "Munich", "München", "Mannheim", "Deutschland", "Sendlinger", "Tor",
    "Goldman", "Sachs", "Decarbonization", "Partners",
    # Company / product names (not transferable candidate skills)
    "OpenAI",
    # Role / title labels that appear in JD prose but aren't discrete skills
    "CTO", "Scientist", "Founder", "Product",
    # Company-invented terms / portmanteaus that aren't real skills
    "Pythonista", "AI/ML",
    # Company-specific product / programme names (not transferable skills)
    "HUB",
    # Solo tokens that are subsumed by a multi-word phrase already in _PHRASES
    # (e.g. "Weights" and "Biases" are noise when "weights & biases" is captured)
    "Weights", "Biases",
    # Generic standalone words that add no signal without their partner token
    "Services", "Web", "Software",
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
    # Company / location names
    "Circula", "BFS", "Riverty", "Bertelsmann", "Dortmund",
    # Solo tokens subsumed by multi-word phrases already in _PHRASES
    "System",   # "system design" is the phrase
    "Cloud",    # "cloud infrastructure" is the phrase
    "Deep",     # "deep learning" is the phrase
    "Model",    # "model deployment" is the phrase
    "Predictive",  # "predictive analytics" is the phrase
    # Untranslated German abbreviations that may leak through LLM translation
    "KI",       # Künstliche Intelligenz = AI (already matched)
    # Generic JD labels and adjectives not representing skills
    "Additionally", "Always", "Basic", "Business", "Completed", "Does",
    "Evaluate", "Fluent", "Innovation", "Know-how", "Knowledge",
    "More", "Nice-to-have", "Plus", "Tech-Skills", "Then", "Teamwork",
    # Plural / inflected forms already covered by their base token or phrase
    "Engineers",   # covered by "Engineer"
    "Shaping",     # verb form, not a skill
    "Thousands",   # from company description ("tausende")
    # Partially-untranslated German compounds
    "KI-based",    # = "AI-based", already covered by "AI"
    # Composite job-title shorthands — not standalone skills
    "ML/DL",
    # Solo token subsumed by "prompt engineering" phrase
    "Prompt",
    # Hyphenated REST variant — CV uses "REST APIs" (space, not hyphen)
    "REST-APIs",
    # Months (appear in date ranges inside JDs)
    "January", "February", "March", "April", "June", "July", "August",
    "September", "October", "November", "December",
    # Tokens fully subsumed by multi-word phrases in _PHRASES
    "Analytics",   # "predictive analytics" is the phrase
    "Computer",    # "computer vision" is the phrase
    "Data",        # "data science" / "data pipeline" are the phrases
    "Face",        # "Hugging Face" is the phrase
    "Hugging",     # "Hugging Face" is the phrase
    "Learning",    # "machine learning" / "deep learning" are the phrases
    "Machine",     # "machine learning" is the phrase
    "Science",     # "data science" is the phrase
    # Generic role / prose labels
    "Act",         # sentence-initial verb
    "Engineer",    # role title, not a discrete skill
    "EU",          # regulatory body reference, not a matchable skill
    "Experience",  # generic label
    "Further",     # filler / transition word
    "German",      # language requirement label, not a keyword to surface
    "Germany",     # location
    "IT",          # too generic (appears in "IT landscape" prose)
    "Pure",        # filler adjective
    "Work",        # generic label
}


def extract_keywords(text: str) -> set[str]:
    """Return a set of likely technical keywords from arbitrary text.

    Output is the original token casing (e.g. "PyTorch", not "pytorch"). For
    matching, callers should casefold both sides.
    """
    tokens = {m.group(1) for m in _TOKEN_RE.finditer(text)}
    tokens = {t for t in tokens if t not in _KEYWORD_STOPWORDS and len(t) >= 2}

    # Collapse bare acronym tokens into their canonical phrase form so that
    # e.g. "ETL" and "etl process" don't both appear as separate keywords.
    tokens = {_TOKEN_ALIASES.get(t, t) for t in tokens}

    lower = text.lower()
    for phrase in _PHRASES:
        if phrase in lower:
            # Normalise to canonical form so plural/variant forms match their base
            canonical = _PHRASE_ALIASES.get(phrase, phrase)
            tokens.add(canonical)

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
    # JD keywords are extracted only from requirement/responsibility chunks so that
    # benefits-section noise ("Coffee", "Parking", "Organic") doesn't pollute the
    # matched/missing keyword lists. Falls back to full jd_text when no chunks exist.
    resume_kw = extract_keywords(resume_text)
    jd_signal_text = (
        " ".join(c.text for c in jd_chunks if c.kind in ("requirement", "responsibility"))
        or jd_text
    )
    jd_kw = extract_keywords(jd_signal_text)
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
        # Two passes: (1) extracted tokens (handles camelCase/acronyms), (2) direct
        # substring check on lowercased requirement text (catches lowercase keywords
        # like "python" that the token regex skips because they aren't capitalised).
        req_kw = extract_keywords(m.requirement)
        if req_kw and any(k.casefold() in r_lower for k in req_kw):
            continue
        req_lower = m.requirement.lower()
        if any(k in req_lower for k in r_lower if len(k) >= 4):
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
            # Skip very short chunks — these are job title lines or company names
            # that slipped through as bullets, not actual achievement statements.
            if len(r_chunk.text.split()) < 5:
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
    # When a JD uses "You'll thrive if..." or "In this role" phrasing, all candidate
    # requirements land in responsibility chunks (not requirement). Fall back across
    # the board so scores aren't artificially zeroed out.
    effective_req = req_score if req_score > 0 else resp_score
    return {
        "core_skills": effective_req,
        "responsibilities": resp_score if resp_score > 0 else req_score,
        "domain": avg_score_for_kind("domain"),
        "ats_keywords": ats_pct,
        "seniority": effective_req,
    }


def _weighted_overall(breakdown: dict[str, int]) -> int:
    total = 0.0
    for key, weight in SCORE_WEIGHTS.items():
        total += breakdown.get(key, 0) * weight
    return int(round(total))
