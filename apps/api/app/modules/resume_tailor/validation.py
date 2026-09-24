"""Deterministic anti-hallucination checks for LLM-generated output.

The tailoring prompt (see generation.py) instructs the model to preserve every
number/metric and never introduce tools, methods, or domains absent from the
original resume — but that's only a prompt-level instruction, never verified.
This module verifies it after the fact, with zero extra LLM calls: reuses
matcher.extract_keywords exactly as-is (no new extraction logic) for the
tech/proper-noun check, plus a plain numeric-token check.

Three entry points sharing one implementation, for prose fields:
    validate_bullet_patch    — a rewritten resume bullet
    validate_headline_skills — the skill segments of profile_headline
    validate_summary         — tailored_summary

Plus one for the LLM-based JD chunking repair path:
    validate_llm_jd_chunks   — see its own docstring

A failing field is dropped (falls back to the untailored original — see
generation.py/rendering.py), never a hard failure of the whole /tailor
request — matches this codebase's universal degrade-gracefully philosophy
(see app/ai/embeddings.py's EmbeddingError handling for the same pattern
applied to a different failure mode).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.modules.resume_tailor.chunker import Chunk, JD_KIND_TO_SECTION
from app.modules.resume_tailor.matcher import extract_keywords

# Numeric tokens: integers, decimals, comma-grouped thousands, optional
# trailing percent sign — e.g. "40%", "1,200", "3.5x" (the "x" multiplier
# suffix is deliberately not required; "3.5" alone still matches and is
# checked against the full resume text).
_NUMBER_RE = re.compile(r"\d[\d,.]*%?")


@dataclass
class FieldValidationResult:
    field_id: str
    ok: bool
    violations: list[str] = field(default_factory=list)


def validate_text_against_resume(
    field_id: str, text: str, resume_full_text: str, *, check_numbers: bool = True,
    extra_grounded_keywords_cf: set[str] | None = None,
) -> FieldValidationResult:
    """Two independent checks, both must pass:

    1. NUMBERS (optional, via check_numbers): every numeric token in text
       must appear verbatim somewhere in resume_full_text (the whole resume,
       not just this field — a number can legitimately be re-emphasized here
       after being introduced elsewhere in the document).
    2. TECH/PROPER-NOUN TOKENS: every keyword extract_keywords() finds in
       text must already be present (case-insensitively) in
       extract_keywords(resume_full_text) — catches fabricated tools,
       frameworks, or domain claims the resume never actually mentions.

    Checked separately because extract_keywords()'s regex requires a leading
    uppercase letter and never matches bare numeric tokens.

    extra_grounded_keywords_cf (casefolded) extends check 2's "already
    present" set beyond literal string presence — see matcher.py::
    _find_grounded_missing_keywords and generation.py's "TERMINOLOGY GAPS"
    prompt block. This is what lets a genuinely-grounded rewording
    ("predictive ML models" -> "predictive analytics") survive the same check
    that blocks an actually-fabricated claim: the keyword still has to have
    been pre-approved via a STRONG embedding match against real resume
    evidence, it just doesn't have to appear as that literal string already.

    The segment-initial word is exempt from check 2. A CV bullet
    conventionally opens with an action verb (reinforced by the tailoring
    prompt's own "adjust only verb / framing" rule) and a tailored summary
    conventionally opens with a role-title noun phrase — extract_keywords()'s
    stopword list only covers present-tense JD-imperative verbs ("Build",
    "Lead"), not resume past-tense bullet verbs ("Built", "Led") or role
    titles, so without this exemption every legitimate verb-only rewrite (or
    a summary that opens with the target role) would be falsely rejected as
    "introducing a new keyword."
    """
    violations: list[str] = []

    if check_numbers:
        for number in set(_NUMBER_RE.findall(text)):
            if number not in resume_full_text:
                violations.append(f"number '{number}' does not appear anywhere in the original resume")

    resume_keywords_casefold = {k.casefold() for k in extract_keywords(resume_full_text)}
    resume_keywords_casefold |= extra_grounded_keywords_cf or set()
    stripped = text.strip()
    first_word = stripped.split(" ", 1)[0] if stripped else ""
    exempt_casefold = {k.casefold() for k in extract_keywords(first_word)}

    for keyword in extract_keywords(text):
        keyword_casefold = keyword.casefold()
        if keyword_casefold in exempt_casefold:
            continue
        if keyword_casefold not in resume_keywords_casefold:
            violations.append(f"keyword '{keyword}' does not appear anywhere in the original resume")

    return FieldValidationResult(field_id=field_id, ok=not violations, violations=violations)


def validate_bullet_patch(
    bullet_id: str, improved_text: str, resume_full_text: str,
    *, extra_grounded_keywords_cf: set[str] | None = None,
) -> FieldValidationResult:
    """A rewritten resume bullet. Numbers and tech keywords both checked."""
    return validate_text_against_resume(
        bullet_id, improved_text, resume_full_text, check_numbers=True,
        extra_grounded_keywords_cf=extra_grounded_keywords_cf,
    )


def validate_headline_skills(
    headline: str, resume_full_text: str, *, extra_grounded_keywords_cf: set[str] | None = None,
) -> FieldValidationResult:
    """profile_headline's format is 'Title | Skill | Skill | Skill' — only the
    skill segments (everything after the first '|') need grounding in the
    resume; the title segment is drawn from the JD and is EXPECTED to be new,
    so it's excluded from the check entirely rather than relying on the
    single-word exemption above."""
    _, _, skills_part = headline.partition("|")
    return validate_text_against_resume(
        "profile_headline", skills_part, resume_full_text, check_numbers=True,
        extra_grounded_keywords_cf=extra_grounded_keywords_cf,
    )


def validate_summary(
    summary: str, resume_full_text: str, *, extra_grounded_keywords_cf: set[str] | None = None,
) -> FieldValidationResult:
    """tailored_summary's tone rules ask for a computed 'N+ years of
    experience' framing derived from the resume's own date ranges — that
    number legitimately won't appear verbatim anywhere in the source text,
    so the numeric check would produce constant false positives here.
    Skipped; the tech-keyword check still applies (catches a summary that
    slips in a skill from the MISSING KEYWORDS list, which the prompt
    explicitly forbids)."""
    return validate_text_against_resume(
        "tailored_summary", summary, resume_full_text, check_numbers=False,
        extra_grounded_keywords_cf=extra_grounded_keywords_cf,
    )


_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


def repair_summary(
    summary: str, resume_full_text: str, *, extra_grounded_keywords_cf: set[str] | None = None,
) -> tuple[str, bool]:
    """Sentence-level repair for a tailored_summary that failed
    validate_summary — a 2-4 sentence summary against a genuinely weak-match
    JD often has the model try to acknowledge a gap in-line ("...though it
    lacks direct computer vision experience"), which mentions a MISSING
    KEYWORD and fails the whole-field check even though the other sentences
    are perfectly grounded. Dropping the entire summary back to the resume's
    untailored original (the prior behavior) throws away real, valid
    tailoring for the sake of one clause. This drops only the offending
    sentence(s) and keeps the rest.

    Returns (repaired_text, ok) — ok=False means the repair itself didn't
    produce a clean, substantial-enough result and the caller should fall
    back to the untailored original, same as before.
    """
    resume_keywords_cf = {k.casefold() for k in extract_keywords(resume_full_text)}
    resume_keywords_cf |= extra_grounded_keywords_cf or set()
    sentences = [s for s in _SENTENCE_BOUNDARY_RE.split(summary.strip()) if s.strip()]

    kept: list[str] = []
    for sentence in sentences:
        stripped = sentence.strip()
        first_word = stripped.split(" ", 1)[0] if stripped else ""
        exempt_cf = {k.casefold() for k in extract_keywords(first_word)}
        ungrounded = any(
            kw.casefold() not in resume_keywords_cf
            for kw in extract_keywords(sentence)
            if kw.casefold() not in exempt_cf
        )
        if not ungrounded:
            kept.append(sentence)

    repaired = " ".join(kept).strip()
    # Require enough left to still read as a real summary, and re-verify it's
    # actually clean now (defensive - the per-sentence check above should
    # already guarantee this).
    if len(repaired) < 60 or not validate_summary(repaired, resume_full_text, extra_grounded_keywords_cf=extra_grounded_keywords_cf).ok:
        return "", False
    return repaired, True


# ── implied_skills_to_add ────────────────────────────────────────────
# Foundational/peer tools ONLY, keyed by a tool the candidate must already
# demonstrably have. Deliberately excludes managed cloud platforms and
# anything needing dedicated infra/training a resume's surface-level usage
# doesn't prove — measured live (2026-09), the prompt instruction alone was
# NOT reliable here: the model copied the ENTIRE missing-keywords list into
# this field verbatim (suggesting AWS SageMaker + Azure OpenAI off nothing
# more than LangChain/RAG experience) rather than genuinely reasoning about
# what's implied. This allowlist is the hard backstop — the LLM's proposal is
# advisory, only a pair listed here is ever actually kept.
_SAFE_IMPLICATIONS: dict[str, set[str]] = {
    "pytorch": {"numpy", "pandas"},
    "tensorflow": {"numpy", "pandas", "keras"},
    "keras": {"tensorflow"},
    "scikit-learn": {"numpy", "pandas"},
    "pandas": {"numpy"},
    "numpy": {"pandas"},
    "langchain": {"langgraph", "llamaindex"},
    "langgraph": {"langchain"},
    "llamaindex": {"langchain"},
    "docker": {"docker compose"},
    "kubernetes": {"helm"},
    "react": {"jsx"},
    "vue": {"vuex", "pinia"},
    "angular": {"rxjs"},
    "postgresql": {"sql"},
    "mysql": {"sql"},
    "sqlite": {"sql"},
    "git": {"github"},
    "pyspark": {"spark"},
    "spark": {"pyspark"},
    "webpack": {"babel"},
    "jest": {"testing library"},
}

_IMPLIED_SKILLS_MAX_ITEMS = 4


def validate_implied_skills(
    implied: list[dict[str, str]], resume_full_text: str,
) -> tuple[list[dict[str, str]], list[str]]:
    """Deterministic filter on the LLM's implied_skills_to_add proposal —
    same "LLM proposes, code disposes" pattern as the other validators here.
    Every item must be a listed peer of a keyword the resume genuinely has
    (extract_keywords, not a guess); everything else is dropped. Returns
    (kept_entries, violation_messages) capped at _IMPLIED_SKILLS_MAX_ITEMS
    total items across all categories."""
    resume_kw_cf = {k.casefold() for k in extract_keywords(resume_full_text)}
    allowed: set[str] = set()
    for have in resume_kw_cf:
        allowed |= _SAFE_IMPLICATIONS.get(have, set())

    kept: list[dict[str, str]] = []
    violations: list[str] = []
    remaining = _IMPLIED_SKILLS_MAX_ITEMS

    for entry in implied:
        category = (entry.get("category") or "").strip()
        raw_items = [i.strip() for i in (entry.get("items") or "").split(",") if i.strip()]
        safe_items = [i for i in raw_items if i.casefold() in allowed]
        dropped = [i for i in raw_items if i.casefold() not in allowed]
        if dropped:
            violations.append(f"implied_skills_to_add: dropped ungrounded {dropped}")
        if not safe_items or not category or remaining <= 0:
            continue
        safe_items = safe_items[:remaining]
        remaining -= len(safe_items)
        kept.append({"category": category, "items": ", ".join(safe_items)})

    return kept, violations


# ── LLM-based JD chunking repair (generation.py::chunk_jd_with_llm_repair) ──

_LLM_CHUNK_KINDS = {"requirement", "responsibility", "domain"}
_LLM_CHUNK_MIN_TEXT_LEN = 4
# Fraction of the source JD's (whitespace-normalized) character count that
# must survive validation for the repair attempt to be trusted at all. Below
# this, the model paraphrased, dropped, or invented too much of the source to
# be safer than just keeping the pathological regex result — a partially-
# broken "repair" that the caller trusts as reliable is worse than a known-bad
# result flagged as degraded.
_LLM_CHUNK_MIN_COVERAGE = 0.5


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def validate_llm_jd_chunks(raw_chunks: list[dict], source_text: str) -> list[Chunk] | None:
    """LLM proposes, code disposes — same pattern as validate_implied_skills,
    applied to generation.py's JD-chunking repair path instead of a prose
    field. Every candidate chunk's "text" must be a genuine, whitespace-
    normalized verbatim substring of the source JD; a chunk that isn't
    (paraphrased, invented, or malformed) is silently dropped, never trusted
    outright. If too little of the source survives that check, the WHOLE
    attempt is rejected (returns None) so the caller falls back to the
    regex chunker's own (known-pathological, but at least real) output.

    Chunks are returned ordered by their position in the source text —
    matches the ordering property the regex chunker naturally provides, in
    case anything downstream implicitly assumes document order.
    """
    if not isinstance(raw_chunks, list) or not raw_chunks:
        return None

    normalized_source = _normalize_for_match(source_text)
    if not normalized_source:
        return None

    kept: list[tuple[int, Chunk]] = []
    covered_chars = 0
    seen_normalized: set[str] = set()

    for entry in raw_chunks:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        text = entry.get("text")
        if kind not in _LLM_CHUNK_KINDS or not isinstance(text, str):
            continue
        normalized = _normalize_for_match(text)
        if len(normalized) < _LLM_CHUNK_MIN_TEXT_LEN or normalized in seen_normalized:
            continue
        pos = normalized_source.find(normalized)
        if pos == -1:
            continue
        seen_normalized.add(normalized)
        covered_chars += len(normalized)
        kept.append((pos, Chunk(kind=kind, section=JD_KIND_TO_SECTION[kind], text=text.strip())))

    if covered_chars / len(normalized_source) < _LLM_CHUNK_MIN_COVERAGE:
        return None

    kept.sort(key=lambda pair: pair[0])
    return [chunk for _, chunk in kept]
