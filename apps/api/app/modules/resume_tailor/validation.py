"""Deterministic anti-hallucination checks for LLM-generated prose fields.

The tailoring prompt (see generation.py) instructs the model to preserve every
number/metric and never introduce tools, methods, or domains absent from the
original resume — but that's only a prompt-level instruction, never verified.
This module verifies it after the fact, with zero extra LLM calls: reuses
matcher.extract_keywords exactly as-is (no new extraction logic) for the
tech/proper-noun check, plus a plain numeric-token check.

Three entry points, one shared implementation:
    validate_bullet_patch    — a rewritten resume bullet
    validate_headline_skills — the skill segments of profile_headline
    validate_summary         — tailored_summary

A failing field is dropped (falls back to the untailored original — see
generation.py/rendering.py), never a hard failure of the whole /tailor
request — matches this codebase's universal degrade-gracefully philosophy
(see app/ai/embeddings.py's EmbeddingError handling for the same pattern
applied to a different failure mode).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

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


def validate_bullet_patch(bullet_id: str, improved_text: str, resume_full_text: str) -> FieldValidationResult:
    """A rewritten resume bullet. Numbers and tech keywords both checked."""
    return validate_text_against_resume(bullet_id, improved_text, resume_full_text, check_numbers=True)


def validate_headline_skills(headline: str, resume_full_text: str) -> FieldValidationResult:
    """profile_headline's format is 'Title | Skill | Skill | Skill' — only the
    skill segments (everything after the first '|') need grounding in the
    resume; the title segment is drawn from the JD and is EXPECTED to be new,
    so it's excluded from the check entirely rather than relying on the
    single-word exemption above."""
    _, _, skills_part = headline.partition("|")
    return validate_text_against_resume("profile_headline", skills_part, resume_full_text, check_numbers=True)


def validate_summary(summary: str, resume_full_text: str) -> FieldValidationResult:
    """tailored_summary's tone rules ask for a computed 'N+ years of
    experience' framing derived from the resume's own date ranges — that
    number legitimately won't appear verbatim anywhere in the source text,
    so the numeric check would produce constant false positives here.
    Skipped; the tech-keyword check still applies (catches a summary that
    slips in a skill from the MISSING KEYWORDS list, which the prompt
    explicitly forbids)."""
    return validate_text_against_resume("tailored_summary", summary, resume_full_text, check_numbers=False)
