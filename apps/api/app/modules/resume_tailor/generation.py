"""All LLM prompt construction/parsing for resume-tailor.

Two independent LLM-facing operations, deliberately split because base_cv_data
must now be dedup'd per resume version, independent of any specific JD (see
models.py's ResumeVersion.base_cv_data):

    generate_base_cv_data(resume_text)  — pure structural parsing, JD-agnostic,
                                           called at most once per resume version.
    generate_tailor_prose(...)          — JD-specific prose (headline, summary,
                                           bullet patches), cached per
                                           (resume_hash, job_hash, prompt_version, model).

Also owns JD language detection/translation (_is_english/_translate_jd) since
that's the other place this module calls the LLM.

Version constants (MATCHER_VERSION/STRUCT_PROMPT_VERSION/PROSE_PROMPT_VERSION)
live here rather than in matcher.py/chunker.py, which stay untouched — bumping
one of these forces fresh cache keys and fresh get_or_create_session lookups
(see repository.py/cache.py), with no manual cache-busting code needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.ai.llm import provider as ai_provider
from app.modules.resume_tailor import cache as resume_cache
from app.modules.resume_tailor.validation import validate_bullet_patch, validate_headline_skills, validate_summary

if TYPE_CHECKING:
    from app.modules.resume_tailor.chunker import Chunk
    from app.modules.resume_tailor.matcher import MatchResult, RewriteCandidate

logger = logging.getLogger(__name__)

# Bumping any of these forces a fresh cache key / fresh get_or_create_session
# lookup — see cache.py and repository.py.
MATCHER_VERSION = "matcher-v1"
STRUCT_PROMPT_VERSION = "struct-v2"  # v2: added other_sections catch-all
PROSE_PROMPT_VERSION = "prose-v2"  # v2: headline/summary now run through validation, not just bullets


# ── JD language detection/translation ───────────────────────────────

# German structural words that rarely appear in English technical text.
# Used to catch German JDs written mostly in ASCII (few umlauts).
_GERMAN_STRUCTURAL_RE = re.compile(
    r"\b(deine?[rns]?|kenntnisse[n]?|aufgaben|werkstudent|studium\b|praktikum|"
    r"bewerbung|erfahrung\b|bereich\b|programmierkenntnisse|abgeschlossenes|"
    r"mehrjährige|solide\b|fundierte|sicherer|vertrautheit|laufendes)\b",
    re.I,
)


def _is_english(text: str) -> bool:
    """Return False if the text appears to be non-English.

    Two-pass check:
    1. Non-ASCII ratio ≥ 1% → non-English (catches umlauts/accents).
    2. German structural word count ≥ 3 → non-English (catches ASCII-heavy
       German JDs like startup postings that use few umlauts).
    """
    if not text:
        return True
    non_ascii = sum(1 for c in text if ord(c) > 127)
    if (non_ascii / len(text)) >= 0.01:
        return False
    german_hits = len(_GERMAN_STRUCTURAL_RE.findall(text))
    return german_hits < 3


async def _translate_jd(text: str) -> str:
    """Translate a non-English JD to English via the configured LLM."""
    system = (
        "Translate the following job description to English. "
        "CRITICAL: Preserve ALL original line breaks, bullet points, and list structure exactly — "
        "each item that was on its own line must remain on its own line after translation. "
        "If the text contains the SAME content in BOTH German AND English already, "
        "output ONLY the English version — do NOT translate the German again or duplicate any section. "
        "Preserve all technical terms, tool names, company names, and section headers exactly. "
        "Return only the translated text with no commentary or preamble."
    )
    return await ai_provider.generate_text(text[:4000], system, max_tokens=4000)


async def translate_jd_if_needed(job_description: str) -> str:
    """English passthrough, or a best-effort translation on failure — never
    raises. Degrades to the original text rather than blocking the request."""
    if _is_english(job_description):
        return job_description
    logger.info("Non-English JD detected — translating to English before analysis")
    try:
        return await _translate_jd(job_description)
    except Exception as exc:
        logger.warning("JD translation failed: %r — proceeding with original text", exc)
        return job_description


# ── Base CV structuring (JD-agnostic, cached per resume version) ───

_SYSTEM_STRUCT_BASE = """You are a professional CV writer. Parse the resume text into a structured JSON object.

CRITICAL RULES — violating any of these produces a broken CV:
1. full_name: Extract the COMPLETE name (e.g. "Sankar Dev Santhosh", NOT just "Sankar"). Never truncate.
2. skills: For EVERY skill category, populate "items" as a non-empty comma-separated string of the actual tools/skills listed. NEVER leave "items" as null, empty string, or an empty list.
3. languages: Copy language entries EXACTLY as written in the resume. Do NOT substitute, add, or remove languages.
4. Completeness: Include ALL experience entries, ALL projects, ALL publications found in the resume. Do not omit any.
5. bullets: Each string in ANY bullets array MUST NOT start with a bullet character (•, -, *, ▪, –). The template adds its own markers. Strip any such prefix before including the text.
6. publications venue: Preserve the COMPLETE venue string verbatim, including any ranking qualifiers (e.g. "Q1-ranked", "Scopus indexed", "SJR"). Never truncate the venue name.
7. featured_project: If the resume contains a section labelled "FEATURED PROJECT", "HIGHLIGHT PROJECT", or similar, you MUST extract it into the `featured_project` field. NEVER leave featured_project null if the resume shows one. Do NOT duplicate it in the `projects` array.
8. other_sections: The categories above (experience/education/skills/projects/publications/languages) don't cover every possible resume section. If the resume has a section that doesn't fit any of them (e.g. "Volunteering", "Patents", "Certifications", "Awards", "References"), put it in `other_sections` with its ORIGINAL heading preserved verbatim. Do NOT drop it, and do NOT force it into an unrelated category above.

Return ONLY this JSON structure (no markdown, no extra text):
{
  "full_name": "string — complete name",
  "job_title": "string — headline/tagline",
  "location": "string (City, Country)",
  "email": "string",
  "phone": "string or null",
  "github": "string or null (path only, e.g. github.com/user)",
  "linkedin": "string or null (path only, e.g. linkedin.com/in/user)",
  "website": "string or null",
  "work_authorization": "string or null",
  "summary": "string — professional summary paragraph",
  "featured_project": {
    "name": "string", "year": "string or null", "tech": "string or null",
    "bullets": ["string"], "results": "string or null"
  },
  "experience": [
    {"title": "string", "company": "string", "location": "string or null",
     "period": "string", "bullets": ["string"]}
  ],
  "education": [
    {"degree": "string", "institution": "string", "location": "string or null",
     "period": "string", "details": "string or null"}
  ],
  "skills": [
    {"category": "string", "items": "SINGLE STRING — skills separated by commas, e.g. \\"Python, PyTorch, Docker\\". NOT an array. NEVER null or empty."}
  ],
  "projects": [
    {"name": "string", "tech": "string or null", "bullets": ["string"]}
  ],
  "publications": [
    {"title": "string", "venue": "string", "year": "string or null"}
  ],
  "languages": ["string — exact language entries from resume"],
  "relocation": "string or null",
  "other_sections": [
    {"heading": "string — the section's ORIGINAL heading from the resume, e.g. \\"Volunteering\\"", "bullets": ["string"]}
  ]
}"""


async def generate_base_cv_data(resume_text: str) -> dict[str, Any]:
    """Pure structural parsing, no JD/tailoring context — called at most once
    per resume_version_id and persisted to resume_versions.base_cv_data."""
    prompt = f"""Parse this resume into the required JSON format.

RESUME TEXT:
{resume_text[:6000]}"""

    raw = await ai_provider.generate_text(prompt, _SYSTEM_STRUCT_BASE, max_tokens=4000)
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as exc:
        raise ValueError(f"Failed to structure resume: malformed LLM JSON response: {exc!r}") from exc


# ── Tailoring prose (JD-specific, cached per resume+job+prompt+model) ──

@dataclass
class TailorProseResult:
    target_role: str = ""
    target_company: str = ""
    profile_headline: str = ""
    tailored_summary: str = ""
    bullet_rewrites: list[dict[str, str]] = field(default_factory=list)
    implied_skills_to_add: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    ai_status: str = "ok"  # "ok" | "degraded"
    ai_provider: str | None = None
    ai_error: str | None = None
    validation_flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_role": self.target_role,
            "target_company": self.target_company,
            "profile_headline": self.profile_headline,
            "tailored_summary": self.tailored_summary,
            "bullet_rewrites": self.bullet_rewrites,
            "implied_skills_to_add": self.implied_skills_to_add,
            "summary": self.summary,
            "ai_status": self.ai_status,
            "ai_provider": self.ai_provider,
            "ai_error": self.ai_error,
            "validation_flags": self.validation_flags,
        }


def _prose_model_label() -> str:
    """Config-time model identity for the prose cache key — reflects what this
    deployment is CURRENTLY configured to use, not necessarily whichever
    provider ends up serving after a fallback (unknowable before the call).
    A provider/model config change naturally busts the cache, which is the
    actual goal."""
    provider = settings.ai_provider.lower().strip()
    if provider == "groq":
        return f"groq:{settings.groq_model}"
    if provider == "openrouter":
        return f"openrouter:{settings.openrouter_model}"
    return provider


def _bullet_ids_for_rewrites(
    resume_chunks: list["Chunk"], rewrite_candidates: list["RewriteCandidate"],
) -> list[str | None]:
    """One id per candidate, aligned BY POSITION with rewrite_candidates
    ('b{index}', where index is the bullet's position in resume_chunks —
    chunk_resume() is a pure function of immutable resume text, so a
    persisted resume_versions.chunks array is fixed forever once created, no
    changes to Chunk/chunker.py needed). None where the candidate's text
    can't be found at all (shouldn't happen since candidates are derived
    from resume_chunks in the first place, but handled defensively).

    Returns a parallel LIST, not a text-keyed dict — deliberately, so two
    candidates with identical bullet text still resolve to two distinct
    (correct) chunk positions instead of the second one silently
    overwriting the first in a shared dict slot.
    """
    text_to_indices: dict[str, list[int]] = {}
    for i, chunk in enumerate(resume_chunks):
        text_to_indices.setdefault(chunk.text, []).append(i)

    claimed: dict[str, int] = {}
    ids: list[str | None] = []
    for rc in rewrite_candidates:
        indices = text_to_indices.get(rc.resume_bullet)
        if not indices:
            ids.append(None)
            continue
        pos = min(claimed.get(rc.resume_bullet, 0), len(indices) - 1)
        claimed[rc.resume_bullet] = pos + 1
        ids.append(f"b{indices[pos]}")
    return ids


_TAILOR_PROSE_SYSTEM = """You are a CV tailoring assistant. The deterministic ATS analysis is already done —
you receive its results and must NOT recompute scores, matched keywords, or missing keywords.

Return ONLY valid JSON in this shape:
{
  "target_role": "<job title from the JD>",
  "target_company": "<company name from the JD>",
  "profile_headline": "<headline in the format: [target job title] | [relevant skill] | [relevant skill] | [relevant skill] — use the exact target job title from the JD as the first segment, then 2–3 skills from the resume most relevant to this specific role>",
  "tailored_summary": "<professional summary paragraph — see tone rules below>",
  "bullet_patches": [{"bullet_id": "<EXACT id shown in brackets in REWRITE CANDIDATES, e.g. b12>", "improved": "<sharpened framing>"}],
  "implied_skills_to_add": [{"category": "<a skills category name matching how this resume already labels its skills>", "items": "<comma-separated foundational tools implied by the candidate's existing tech stack>"}],
  "summary": "<1-paragraph honest fit assessment noting strengths and real gaps>"
}

Hard rules:
- bullet_patches: ONLY patch bullets from the REWRITE CANDIDATES list. Echo the EXACT bullet_id shown in brackets — do NOT retype the original bullet text.
  * PRESERVE every number, percentage, and metric from the original
  * NEVER add tools, methods, or domains absent from the original
  * Adjust only verb / framing / emphasis — the evidence must stay identical
- implied_skills_to_add: for any tool or library in the MISSING KEYWORDS list that is clearly implied by the candidate's existing tech stack (e.g. Pandas/NumPy implied by PyTorch/ML work), add it under a category name that matches this resume's own skills section labelling. Only do this for standard foundational tools — never invent specialised domain experience. Leave empty if nothing qualifies.
- profile_headline: lead with the exact job title from the JD, then 2–3 of the candidate's REAL skills most relevant to THIS SPECIFIC ROLE. Prefer specific technical skills (e.g. RAG, NLP, LangChain, Transformers, EU AI Act) over generic acronyms — NEVER use "AI", "ML", or "Machine Learning" as a standalone headline segment; they are redundant when the job title already implies them. Draw from MATCHED KEYWORDS and resume skills when they clearly overlap the JD's domain. Never add skills the resume doesn't show.
- tailored_summary TONE AND CONTENT — strict CV style, not cover letter style:
  * Write in NOMINATIVE STYLE ONLY — no pronouns at all. Do NOT use "I", "my", "their", "they", "this candidate", "the candidate". Start directly with a noun phrase: "Applied AI Engineer with 3+ years…".
  * NO cover-letter phrases: "I am confident", "I am excited", "I look forward to", "I believe".
  * NO vague filler: "drive innovation", "leveraging expertise", "improve complex workflows", "passionate about".
  * Lead with years of experience and core specialty, e.g. "Applied AI Engineer with 3+ years of experience building..."
  * Include at least ONE specific achievement from the resume (a metric, a project name, or a publication). Make it feel like THIS candidate, not any AI engineer.
  * Reframe genuine transferable experience for this specific role. Never claim domain expertise the resume does not show.
  * Write in your own words — do NOT copy or paraphrase sentence fragments from the JD requirements. The summary must read as the candidate's own story, not a reflection of the job posting.
  * NEVER mention any skill from the MISSING KEYWORDS list — those are absent from the resume.
- summary: ground the fit assessment in the provided CRITICAL GAPS and TRANSFERABLE STRENGTHS.
- Return ONLY valid JSON, no markdown fences."""


async def _generate_tailor_prose_uncached(
    resume_text: str,
    resume_chunks: list["Chunk"],
    job_description: str,
    analysis: "MatchResult",
) -> TailorProseResult:
    bullet_ids = _bullet_ids_for_rewrites(resume_chunks, analysis.rewrite_candidates)
    rewrites_block = (
        "\n".join(
            f"- [{bullet_id}] ORIGINAL: {rc.resume_bullet}\n  TARGET REQUIREMENT: {rc.target_requirement}"
            for rc, bullet_id in zip(analysis.rewrite_candidates, bullet_ids)
            if bullet_id is not None
        )
        or "(no bullets in the rewrite band — leave bullet_patches empty)"
    )
    transferable_block = "; ".join(analysis.transferable_strengths[:6]) or "(none)"
    critical_block = "; ".join(analysis.critical_missing[:6]) or "(none)"
    missing_block = ", ".join(analysis.missing_keywords) or "(none)"
    matched_block = ", ".join(analysis.matched_keywords[:15]) or "(none)"

    prompt = f"""DETERMINISTIC ANALYSIS (do not recompute, just use):
OVERALL SCORE: {analysis.overall_score}
SCORE BREAKDOWN: {json.dumps(analysis.score_breakdown)}
MATCHED KEYWORDS (use these to pick headline skills — prefer the ones most role-relevant): {matched_block}
TRANSFERABLE STRENGTHS: {transferable_block}
CRITICAL GAPS (do not invent experience to cover these): {critical_block}
MISSING KEYWORDS — absent from resume, do not mention in any prose field: {missing_block}

REWRITE CANDIDATES (only patch these — echo the bracketed id, not the text):
{rewrites_block}

JOB DESCRIPTION:
{job_description[:2500]}

RESUME (for extracting target_role/target_company and grounding prose only):
{resume_text[:3500]}"""

    try:
        raw, provider = await ai_provider.generate_text_with_provider(prompt, _TAILOR_PROSE_SYSTEM, max_tokens=1200)
    except ai_provider.AIGenerationError as exc:
        logger.warning("Tailor prose generation failed: %r — returning deterministic analysis only", exc)
        return TailorProseResult(ai_status="degraded", ai_error=str(exc))

    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        parsed = json.loads(raw[start:end])
    except Exception:
        logger.warning("LLM tailor prose returned malformed JSON: %r", raw[:300])
        return TailorProseResult(ai_status="degraded", ai_provider=provider, ai_error="malformed JSON response")

    validation_flags: list[str] = []

    bullet_text_by_id = {f"b{i}": chunk.text for i, chunk in enumerate(resume_chunks)}
    bullet_rewrites: list[dict[str, str]] = []
    for patch in parsed.get("bullet_patches") or []:
        bullet_id = patch.get("bullet_id")
        improved = patch.get("improved")
        original = bullet_text_by_id.get(bullet_id) if bullet_id else None
        if not improved or original is None:
            continue
        result = validate_bullet_patch(bullet_id, improved, resume_text)
        if not result.ok:
            validation_flags.append(f"{bullet_id}: {'; '.join(result.violations)}")
            continue
        bullet_rewrites.append({"original": original, "improved": improved})

    # profile_headline/tailored_summary get the same grounding check as
    # bullets — a failing field is dropped (empty string) rather than
    # rejecting the whole response; apply_tailoring_overlay() already treats
    # an empty profile_headline/tailored_summary as "keep the resume's own
    # untailored value," so this composes for free, no extra fallback logic.
    profile_headline = parsed.get("profile_headline", "")
    if profile_headline:
        headline_check = validate_headline_skills(profile_headline, resume_text)
        if not headline_check.ok:
            validation_flags.append(f"profile_headline: {'; '.join(headline_check.violations)}")
            profile_headline = ""

    tailored_summary = parsed.get("tailored_summary", "")
    if tailored_summary:
        summary_check = validate_summary(tailored_summary, resume_text)
        if not summary_check.ok:
            validation_flags.append(f"tailored_summary: {'; '.join(summary_check.violations)}")
            tailored_summary = ""

    return TailorProseResult(
        target_role=parsed.get("target_role", ""),
        target_company=parsed.get("target_company", ""),
        profile_headline=profile_headline,
        tailored_summary=tailored_summary,
        bullet_rewrites=bullet_rewrites,
        implied_skills_to_add=parsed.get("implied_skills_to_add") or [],
        summary=parsed.get("summary", ""),
        ai_status="ok",
        ai_provider=provider,
        validation_flags=validation_flags,
    )


async def generate_tailor_prose(
    user_id: str,
    resume_hash: str,
    job_hash: str,
    resume_text: str,
    resume_chunks: list["Chunk"],
    job_description: str,
    analysis: "MatchResult",
) -> TailorProseResult:
    """Cached, single-flight-guarded wrapper around _generate_tailor_prose_uncached.
    Never raises — a total AI outage degrades to an empty-prose TailorProseResult
    (ai_status="degraded") rather than failing the whole /tailor request."""
    model_label = _prose_model_label()

    cached = await resume_cache.get_prose_cache(user_id, resume_hash, job_hash, PROSE_PROMPT_VERSION, model_label)
    if cached is not None:
        return TailorProseResult(**cached)

    try:
        is_leader = await resume_cache.acquire_prose_lock(user_id, resume_hash, job_hash, PROSE_PROMPT_VERSION)
    except Exception:
        is_leader = True

    if not is_leader:
        waited = 0.0
        while waited < resume_cache.PROSE_SINGLE_FLIGHT_MAX_WAIT_SECONDS:
            await asyncio.sleep(resume_cache.PROSE_SINGLE_FLIGHT_POLL_INTERVAL_SECONDS)
            waited += resume_cache.PROSE_SINGLE_FLIGHT_POLL_INTERVAL_SECONDS
            cached = await resume_cache.get_prose_cache(user_id, resume_hash, job_hash, PROSE_PROMPT_VERSION, model_label)
            if cached is not None:
                return TailorProseResult(**cached)
        # Timed out waiting for the leader — proceed and call the LLM anyway
        # rather than hang forever, same fail-open philosophy as every other
        # limiter/lock in this codebase.

    result = await _generate_tailor_prose_uncached(resume_text, resume_chunks, job_description, analysis)

    if result.ai_status == "ok":
        try:
            await resume_cache.set_prose_cache(user_id, resume_hash, job_hash, PROSE_PROMPT_VERSION, model_label, result.as_dict())
        except Exception:
            pass

    return result
