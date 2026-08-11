"""AI endpoints — resume tailor + CV generation.

All endpoints stream responses via Server-Sent Events.
Rate limits enforced per user per tool via Upstash Redis.
"""

import asyncio
import base64
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

import fitz  # PyMuPDF
import httpx
import numpy as np
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, Response, HTMLResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.ext.asyncio import AsyncSession
from weasyprint import HTML as WeasyHTML

from app.core.config import settings
from app.core.database import get_db
from app.services.cache import check_rate_limit, get_cached, set_cached
from app.modules.resume_tailor.cache import (
    compute_resume_hash,
    deserialize_embeddings,
    get_resume_cache,
    serialize_embeddings,
    update_resume_cache,
)
from app.modules.resume_tailor.chunker import chunk_jd, chunk_resume, chunks_from_dicts, chunks_to_dicts, clean_jd_text
from app.modules.resume_tailor.matcher import match_resume_to_jd
from app.modules.resume_tailor import service as resume_tailor_service
from app.ai.embeddings import EmbeddingError, embed
from app.core.security import get_current_user_id
from app.ai.llm import provider as ai_provider
from app.shared.utils import _rl_error
from app.modules.usage.service import record_event as record_tool_usage

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

_BULLET_PREFIX = re.compile(r"^[\s•\-\*▪–]+")

# Private/link-local IP ranges that must not be fetched (SSRF guard)
_PRIVATE_NETS = re.compile(
    r"^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|169\.254\.|::1$|fc|fd)",
    re.IGNORECASE,
)


def _safe_photo_url(url: str | None) -> str | None:
    """Return url only if it is a public https URL. Returns None otherwise."""
    if not url:
        return None
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        return None
    host = parsed.hostname or ""
    if _PRIVATE_NETS.match(host):
        return None
    return url

TEMPLATE_REGISTRY: dict[str, dict] = {
    "standard":             {"label": "Standard",             "desc": "Clean, professional single-column layout",         "font": "Arial, sans-serif",          "columns": 1, "file": "template_standard.html"},
    "modern":               {"label": "Modern",               "desc": "Two-column layout with sidebar for contact info",   "font": "Arial, sans-serif",          "columns": 2, "file": "template_modern.html"},
    "creative":             {"label": "Creative",             "desc": "Timeline-based design with icons and visual elements","font": "Arial, sans-serif",         "columns": 1, "file": "template_creative.html"},
    "classic":              {"label": "Classic",              "desc": "Traditional format with clean typography",          "font": "Times New Roman, serif",     "columns": 1, "file": "template_classic_new.html"},
    "balanced":             {"label": "Balanced",             "desc": "Professional layout with clear section divisions",  "font": "Arial, sans-serif",          "columns": 1, "file": "template_balanced.html"},
    "minimalist":           {"label": "Minimalist",           "desc": "Clean, modern design with subtle borders and spacing","font": "system-ui, sans-serif",    "columns": 1, "file": "template_minimalist.html"},
    "professional":         {"label": "Professional",         "desc": "Executive-style layout with elegant formatting",    "font": "Arial, sans-serif",          "columns": 1, "file": "template_professional.html"},
    "corporate":            {"label": "Corporate",            "desc": "Two-column corporate layout with header contact section","font": "Arial, sans-serif",     "columns": 2, "file": "template_corporate.html"},
    "bold":                 {"label": "Bold",                 "desc": "Bold styling with clear hierarchy and modern design","font": "Arial, sans-serif",         "columns": 1, "file": "template_bold.html"},
    "slate":                {"label": "Slate",                "desc": "Two-column slate accent layout with modern contrast","font": "Arial, sans-serif",         "columns": 2, "file": "template_slate.html"},
    "professional_compact": {"label": "Professional Compact", "desc": "Centered header with ALL CAPS section titles and clean hierarchy","font": "Arial, sans-serif","columns": 1, "file": "template_professional_compact.html"},
    "executive":            {"label": "Executive",            "desc": "Two-column sidebar layout with details panel",      "font": "Arial, sans-serif",          "columns": 2, "file": "template_executive.html"},
    "insight":              {"label": "Insight",              "desc": "Executive sidebar layout with navy accents and reference cards","font": "Inter, sans-serif","columns": 2, "file": "template_insight.html"},
    "atelier":              {"label": "Atelier",              "desc": "Editorial two-column layout inspired by artisan portfolios","font": "Georgia, serif",      "columns": 2, "file": "template_atelier.html"},
    "elegant":              {"label": "Elegant",              "desc": "Refined single-column with accent separators and strong hierarchy","font": "Georgia, serif","columns": 1, "file": "template_elegant.html"},
    "aqua":                 {"label": "Aqua",                 "desc": "Two-column layout with a soft header band and clear sectioning","font": "Arial, sans-serif","columns": 2, "file": "template_aqua.html"},
    "lebenslauf":           {"label": "Lebenslauf (DE)",      "desc": "Traditional German CV with photo sidebar",          "font": "Arial, sans-serif",          "columns": 2, "file": "template_classic.html", "requires_photo": True},
}


# ── Resume Tailor ─────────────────────────────────────────────────

@router.post("/tailor")
async def tailor_resume(
    request: Request,
    resume: UploadFile = File(...),
    job_description: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_current_user_id(request, db)
    allowed, _ = await check_rate_limit(user_id, "resume", settings.rate_limit_resume_per_day)
    if not allowed:
        raise _rl_error("Resume Tailor", settings.rate_limit_resume_per_day)
    await record_tool_usage(db, user_id, "resume-tailor")

    _MAX_PDF_BYTES = 5 * 1024 * 1024  # 5 MB
    pdf_bytes = await resume.read(_MAX_PDF_BYTES + 1)
    if len(pdf_bytes) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF must be ≤ 5 MB")
    resume_hash = compute_resume_hash(pdf_bytes)

    # Cache hit: skip PyMuPDF re-parse. The cache survives 30 days, so subsequent
    # tailoring runs against new JDs reuse the extracted text for free.
    cached = await get_resume_cache(user_id, resume_hash)
    if cached and cached.get("text"):
        resume_text = cached["text"]
    else:
        def _extract_text() -> str:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            return "\n".join(page.get_text() for page in doc)

        try:
            resume_text = await asyncio.to_thread(_extract_text)
        except Exception:
            raise HTTPException(status_code=400, detail="Could not parse PDF. Ensure it's a valid PDF file.")
        await update_resume_cache(user_id, resume_hash, text=resume_text)

    # Legacy short-TTL key — generate-pdf still reads from here without needing the hash.
    await set_cached(f"resume_text:{user_id}", resume_text, ttl_seconds=7200)

    # ─── Resume chunks + embeddings (cached per resume hash) ─────────
    resume_chunks_dicts = (cached or {}).get("chunks") if cached else None
    if resume_chunks_dicts:
        resume_chunks = chunks_from_dicts(resume_chunks_dicts)
        resume_embeddings = deserialize_embeddings((cached or {}).get("embeddings"))
    else:
        resume_chunks = chunk_resume(resume_text)
        resume_embeddings = np.zeros((0, 0), dtype="float32")

    # Re-embed if embeddings are absent — covers first run and cache entries
    # written before embeddings were available (e.g. after a provider outage).
    if resume_embeddings.size == 0:
        try:
            resume_embeddings = await embed([c.text for c in resume_chunks], purpose="matching")
        except EmbeddingError as exc:
            logger.warning("Resume embeddings unavailable: %r — falling back to keyword-only matching", exc)
            resume_embeddings = np.zeros((0, 0), dtype="float32")
        await update_resume_cache(
            user_id, resume_hash,
            chunks=chunks_to_dicts(resume_chunks),
            embeddings=serialize_embeddings(resume_embeddings) if resume_embeddings.size > 0 else [],
        )

    # ─── JD language normalisation (translate to English if needed) ──────
    jd_for_processing = job_description
    if not _is_english(job_description):
        logger.info("Non-English JD detected — translating to English before analysis")
        try:
            jd_for_processing = await _translate_jd(job_description)
        except Exception as exc:
            logger.warning("JD translation failed: %r — proceeding with original text", exc)

    # ─── JD chunks + embeddings (always fresh) ────────────────────────
    jd_text_clean = clean_jd_text(jd_for_processing)
    jd_chunks = chunk_jd(jd_text_clean)
    try:
        jd_embeddings = await embed([c.text for c in jd_chunks], purpose="matching") if jd_chunks else _empty_array()
    except EmbeddingError as exc:
        logger.warning("JD embeddings unavailable: %r — falling back to keyword-only matching", exc)
        jd_embeddings = _empty_array()

    # ─── Deterministic match + scoring + gap analysis ─────────────────
    analysis = match_resume_to_jd(
        resume_chunks=resume_chunks,
        resume_embeddings=resume_embeddings,
        jd_chunks=jd_chunks,
        jd_embeddings=jd_embeddings,
        resume_text=resume_text,
        jd_text=jd_text_clean,
    )

    # ─── LLM call — only for AI-generated prose ───────────────────────
    ai_fields = await _generate_tailor_prose(resume_text, jd_for_processing, analysis)

    # ─── Merge deterministic + AI into the wire format the frontend expects ──
    response_payload = {
        # AI-generated
        "target_role": ai_fields.get("target_role", ""),
        "target_company": ai_fields.get("target_company", ""),
        "profile_headline": ai_fields.get("profile_headline", ""),
        "tailored_summary": ai_fields.get("tailored_summary", ""),
        "bullet_rewrites": ai_fields.get("bullet_rewrites", []),
        "summary": ai_fields.get("summary", ""),

        # Deterministic — authoritative, never produced by LLM
        "match_score": analysis.overall_score,
        "matched_keywords": analysis.matched_keywords,
        "missing_keywords": [
            {"keyword": kw, "suggested_placement": "skills"} for kw in analysis.missing_keywords
        ],
        "score_breakdown": analysis.score_breakdown,
        "transferable_strengths": analysis.transferable_strengths,
        "critical_missing": analysis.critical_missing,
        "matches": [m.as_dict() for m in analysis.matches],
        "degraded": analysis.degraded,
    }

    # Wrap in StreamingResponse so frontend's existing reader loop keeps working;
    # we just emit one chunk. The frontend regex-extracts the JSON object.
    body = json.dumps(response_payload)

    async def emit():
        yield body

    return StreamingResponse(
        emit(),
        media_type="application/json",
        headers={"X-Resume-Hash": resume_hash},
    )


def _empty_array():
    return np.zeros((0, 0), dtype="float32")


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


async def _generate_tailor_prose(
    resume_text: str,
    job_description: str,
    analysis,  # MatchResult — typed loosely to avoid an import cycle
) -> dict:
    """One small LLM call. Receives the deterministic analysis as context and
    returns only the AI-generated fields. Keeps the LLM scope narrow so cheaper
    open-weight models (Llama 3.3 via Groq) can hit it reliably.
    """
    rewrites_block = (
        "\n".join(f"- ORIGINAL: {r.resume_bullet}\n  TARGET REQUIREMENT: {r.target_requirement}"
                  for r in analysis.rewrite_candidates)
        or "(no bullets in the rewrite band — leave bullet_rewrites empty)"
    )
    transferable_block = "; ".join(analysis.transferable_strengths[:6]) or "(none)"
    critical_block = "; ".join(analysis.critical_missing[:6]) or "(none)"
    missing_block = ", ".join(analysis.missing_keywords) or "(none)"
    matched_block = ", ".join(analysis.matched_keywords[:15]) or "(none)"

    system = """You are a CV tailoring assistant. The deterministic ATS analysis is already done —
you receive its results and must NOT recompute scores, matched keywords, or missing keywords.

Return ONLY valid JSON in this shape:
{
  "target_role": "<job title from the JD>",
  "target_company": "<company name from the JD>",
  "profile_headline": "<headline in the format: [target job title] | [relevant skill] | [relevant skill] | [relevant skill] — use the exact target job title from the JD as the first segment, then 2–3 skills from the resume most relevant to this specific role>",
  "tailored_summary": "<professional summary paragraph — see tone rules below>",
  "bullet_rewrites": [{"original": "<EXACT original bullet from REWRITE CANDIDATES>", "improved": "<sharpened framing>"}],
  "summary": "<1-paragraph honest fit assessment noting strengths and real gaps>"
}

Hard rules:
- bullet_rewrites: ONLY rewrite bullets from the REWRITE CANDIDATES list. Use the original verbatim as the "original" field.
  * PRESERVE every number, percentage, and metric from the original
  * NEVER add tools, methods, or domains absent from the original
  * Adjust only verb / framing / emphasis — the evidence must stay identical
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

    prompt = f"""DETERMINISTIC ANALYSIS (do not recompute, just use):
OVERALL SCORE: {analysis.overall_score}
SCORE BREAKDOWN: {json.dumps(analysis.score_breakdown)}
MATCHED KEYWORDS (use these to pick headline skills — prefer the ones most role-relevant): {matched_block}
TRANSFERABLE STRENGTHS: {transferable_block}
CRITICAL GAPS (do not invent experience to cover these): {critical_block}
MISSING KEYWORDS — absent from resume, do not mention in any prose field: {missing_block}

REWRITE CANDIDATES (only rewrite these — copy "ORIGINAL" verbatim):
{rewrites_block}

JOB DESCRIPTION:
{job_description[:2500]}

RESUME (for extracting target_role/target_company and grounding prose only):
{resume_text[:3500]}"""

    raw = await ai_provider.generate_text(prompt, system, max_tokens=1200)
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        logger.warning("LLM tailor prose returned malformed JSON: %r", raw[:300])
        return {}


# ── CV data helpers ───────────────────────────────────────────────

_SYSTEM_STRUCT = """You are a professional CV writer. Parse the resume text into a structured JSON object.

CRITICAL RULES — violating any of these produces a broken CV:
1. full_name: Extract the COMPLETE name (e.g. "Sankar Dev Santhosh", NOT just "Sankar"). Never truncate.
2. skills: For EVERY skill category, populate "items" as a non-empty comma-separated string of the actual tools/skills listed. NEVER leave "items" as null, empty string, or an empty list.
3. languages: Copy language entries EXACTLY as written in the resume. Do NOT substitute, add, or remove languages.
4. Completeness: Include ALL experience entries, ALL projects, ALL publications found in the resume. Do not omit any.
5. bullet_rewrites: Replace each original bullet with its improved version verbatim — do not skip any provided rewrite.
6. If a TAILORED HEADLINE is provided, use it as job_title. If a TAILORED SUMMARY is provided, use it as summary — copy it VERBATIM, do NOT modify it to weave in keywords.
7. bullets: Each string in ANY bullets array MUST NOT start with a bullet character (•, -, *, ▪, –). The template adds its own markers. Strip any such prefix before including the text.
8. publications venue: Preserve the COMPLETE venue string verbatim, including any ranking qualifiers (e.g. "Q1-ranked", "Scopus indexed", "SJR"). Never truncate the venue name.
9. featured_project: If the resume contains a section labelled "FEATURED PROJECT", "HIGHLIGHT PROJECT", or similar, you MUST extract it into the `featured_project` field. NEVER leave featured_project null if the resume shows one. Do NOT duplicate it in the `projects` array.
10. missing keywords: For any tool or library in the MISSING KEYWORDS list that is clearly implied by the candidate's existing tech stack (e.g. Pandas/NumPy implied by PyTorch/ML work), add it to the most relevant existing skill category's items string. Only do this for standard foundational tools — never invent specialised domain experience.

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
    {"category": "string", "items": "SINGLE STRING — skills separated by commas, e.g. \"Python, PyTorch, Docker\". NOT an array. NEVER null or empty."}
  ],
  "projects": [
    {"name": "string", "tech": "string or null", "bullets": ["string"]}
  ],
  "publications": [
    {"title": "string", "venue": "string", "year": "string or null"}
  ],
  "languages": ["string — exact language entries from resume"],
  "relocation": "string or null"
}"""


def _normalize_cv_data(cv_data: dict) -> None:
    """Strip bullet prefixes and normalise skill items in-place."""
    for section_key in ("featured_project",):
        if cv_data.get(section_key) and isinstance(cv_data[section_key].get("bullets"), list):
            cv_data[section_key]["bullets"] = [
                _BULLET_PREFIX.sub("", b) for b in cv_data[section_key]["bullets"]
            ]
    for section_key in ("experience", "projects"):
        for entry in cv_data.get(section_key) or []:
            if isinstance(entry.get("bullets"), list):
                entry["bullets"] = [_BULLET_PREFIX.sub("", b) for b in entry["bullets"]]
    if cv_data.get("skills"):
        normalised = []
        for s in cv_data["skills"]:
            items = s.get("items")
            if isinstance(items, list):
                items = ", ".join(str(i).strip(" •·-–\t") for i in items if str(i).strip(" •·-–\t"))
            elif items is not None:
                items = str(items)
                items = re.sub(r"<[^>]+>", " ", items)
                lines = [ln.strip(" •·-–\t") for ln in items.splitlines() if ln.strip(" •·-–\t")]
                if len(lines) > 1:
                    items = ", ".join(lines)
                items = items.strip()
            if items:
                normalised.append({**s, "items": items})
        cv_data["skills"] = normalised


async def _apply_profile_overlay(cv_data: dict, profile: dict, profile_headline: str, template_id: str) -> None:
    """Overlay authoritative profile contact fields onto cv_data in-place."""
    profile_name = (profile.get("full_name") or "").strip()
    if profile_name and " " in profile_name:
        cv_data["full_name"] = profile_name
    if not profile_headline and profile.get("job_title"):
        cv_data["job_title"] = profile["job_title"]
    cv_email = profile.get("cv_email") or profile.get("email")
    if cv_email:
        cv_data["email"] = cv_email
    if profile.get("phone"):
        cv_data["phone"] = profile["phone"]
    if profile.get("linkedin_url"):
        cv_data["linkedin"] = profile["linkedin_url"]
    if profile.get("github_url"):
        cv_data["github"] = profile["github_url"]
    if profile.get("website_url"):
        cv_data["website"] = profile["website_url"]
    if profile.get("work_authorization"):
        cv_data["work_authorization"] = profile["work_authorization"]
    if profile.get("address_city"):
        parts = [profile["address_city"]]
        if profile.get("address_country"):
            parts.append(profile["address_country"])
        cv_data["location"] = ", ".join(parts)

    photo_base64 = None
    if template_id == "lebenslauf":
        safe_url = _safe_photo_url(profile.get("cv_photo_url"))
        if safe_url:
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    r = await client.get(safe_url)
                    if r.status_code == 200:
                        photo_base64 = base64.b64encode(r.content).decode()
            except Exception:
                pass
    cv_data["photo_base64"] = photo_base64
    cv_data["date_of_birth"] = profile.get("date_of_birth")
    cv_data["nationality"] = profile.get("nationality")


async def _llm_structure_resume(resume_text: str, analysis: dict) -> dict:
    """Call LLM once to parse resume text + analysis into structured cv_data JSON."""
    bullet_rewrites = {r["original"]: r["improved"] for r in (analysis.get("bullet_rewrites") or [])}
    missing_kw = [m["keyword"] for m in (analysis.get("missing_keywords") or [])]
    target_role = analysis.get("target_role") or ""
    target_company = analysis.get("target_company") or ""
    profile_headline = analysis.get("profile_headline") or ""
    tailored_summary = analysis.get("tailored_summary") or ""

    tailoring_block = ""
    if target_role or target_company:
        tailoring_block += f"\nTARGET ROLE: {target_role} at {target_company}"
    if profile_headline:
        tailoring_block += f"\nTAILORED HEADLINE TO USE AS job_title: {profile_headline}"
    if tailored_summary:
        tailoring_block += f"\nTAILORED SUMMARY TO USE AS summary: {tailored_summary}"

    rewrites_block = "\n".join(f'  ORIGINAL: {o}\n  IMPROVED: {i}' for o, i in bullet_rewrites.items()) if bullet_rewrites else "None"
    kw_block = ", ".join(missing_kw) if missing_kw else "None"

    prompt = f"""Parse this resume into the required JSON format.
{tailoring_block}

BULLET REWRITES TO APPLY (replace originals with improved versions verbatim):
{rewrites_block}

MISSING KEYWORDS — add foundational tools (e.g. Pandas, NumPy, SciKit-learn) to the relevant skills category if implied by existing tech stack. Do NOT invent domain experience:
{kw_block}

IMPORTANT: If the resume has a "FEATURED PROJECT" section, it MUST be in featured_project (not in projects).

RESUME TEXT:
{resume_text[:6000]}"""

    raw = await ai_provider.generate_text(prompt, _SYSTEM_STRUCT, max_tokens=4000)
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        cv_data = json.loads(raw[start:end])
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to structure resume. Please try again.")

    if tailored_summary:
        cv_data["summary"] = tailored_summary

    return cv_data


# ── CV PDF Generation ─────────────────────────────────────────────

@router.get("/tailor/templates")
async def list_templates():
    """Return template registry metadata (no internal file paths)."""
    return {
        "templates": [
            {"id": k, **{kk: vv for kk, vv in v.items() if kk != "file"}}
            for k, v in TEMPLATE_REGISTRY.items()
        ]
    }


@router.post("/tailor/structure-resume")
async def structure_resume(request: Request, body: dict, db: AsyncSession = Depends(get_db)):
    """LLM-structure the cached resume into cv_data JSON. Called once when the editor loads."""
    user_id = await get_current_user_id(request, db)
    allowed, _ = await check_rate_limit(user_id, "resume", settings.rate_limit_resume_per_day)
    if not allowed:
        raise _rl_error("Resume Tailor", settings.rate_limit_resume_per_day)

    resume_text = await get_cached(f"resume_text:{user_id}")
    if not resume_text:
        raise HTTPException(
            status_code=400,
            detail="No recent analysis found. Please run the Resume Tailor analysis first.",
        )

    analysis = body.get("analysis") or {}
    template_id = body.get("template_id", "standard")
    if template_id not in TEMPLATE_REGISTRY:
        template_id = "standard"

    cv_data = await _llm_structure_resume(resume_text, analysis)
    _normalize_cv_data(cv_data)

    profile = await resume_tailor_service.get_profile_for_overlay(db, user_id)
    profile_headline = analysis.get("profile_headline") or ""
    await _apply_profile_overlay(cv_data, profile, profile_headline, template_id)

    return {"cv_data": cv_data}


@router.post("/tailor/generate-pdf")
async def generate_cv_pdf(request: Request, body: dict, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
    allowed, _ = await check_rate_limit(user_id, "resume", settings.rate_limit_resume_per_day)
    if not allowed:
        raise _rl_error("Resume Tailor", settings.rate_limit_resume_per_day)

    template_id = body.get("template_id", "standard")
    if template_id not in TEMPLATE_REGISTRY:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown template_id '{template_id}'. Valid: {', '.join(TEMPLATE_REGISTRY)}",
        )

    cv_data_override = body.get("cv_data")

    if cv_data_override:
        cv_data = dict(cv_data_override)
        _normalize_cv_data(cv_data)
        if template_id == "lebenslauf":
            profile = await resume_tailor_service.get_profile_photo_fields(db, user_id)
            photo_base64 = None
            safe_url = _safe_photo_url(profile.get("cv_photo_url"))
            if safe_url:
                try:
                    async with httpx.AsyncClient(timeout=8) as client:
                        r = await client.get(safe_url)
                        if r.status_code == 200:
                            photo_base64 = base64.b64encode(r.content).decode()
                except Exception:
                    pass
            cv_data["photo_base64"] = photo_base64
            cv_data["date_of_birth"] = profile.get("date_of_birth")
            cv_data["nationality"] = profile.get("nationality")
        else:
            cv_data.setdefault("photo_base64", None)
            cv_data.setdefault("date_of_birth", None)
            cv_data.setdefault("nationality", None)
    else:
        resume_text = await get_cached(f"resume_text:{user_id}")
        if not resume_text:
            raise HTTPException(
                status_code=400,
                detail="No recent analysis found. Please run the Resume Tailor analysis first.",
            )
        analysis = body.get("analysis") or {}
        cv_data = await _llm_structure_resume(resume_text, analysis)
        _normalize_cv_data(cv_data)

        profile = await resume_tailor_service.get_profile_for_overlay(db, user_id)
        profile_headline = analysis.get("profile_headline") or ""
        await _apply_profile_overlay(cv_data, profile, profile_headline, template_id)

    logger.info("CV render: template=%s name=%s", template_id, cv_data.get("full_name"))

    template_file = TEMPLATE_REGISTRY[template_id]["file"]
    tmpl = _jinja_env.get_template(template_file)
    html_out = tmpl.render(**cv_data)

    pdf_bytes = await asyncio.to_thread(lambda: WeasyHTML(string=html_out).write_pdf())

    opportunity_id = body.get("opportunity_id")
    if opportunity_id:
        await resume_tailor_service.save_resume_artifact(
            db, user_id, opportunity_id, template_id, (body.get("analysis") or {}).get("match_score")
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="tailored_cv_{template_id}.pdf"'},
    )


@router.post("/tailor/preview-html")
async def preview_cv_html(request: Request, body: dict, db: AsyncSession = Depends(get_db)):
    """Render CV template to HTML for live preview — no PDF conversion, no rate limit."""
    user_id = await get_current_user_id(request, db)

    template_id = body.get("template_id", "standard")
    if template_id not in TEMPLATE_REGISTRY:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown template_id '{template_id}'. Valid: {', '.join(TEMPLATE_REGISTRY)}",
        )

    cv_data_override = body.get("cv_data")
    if not cv_data_override:
        raise HTTPException(status_code=400, detail="cv_data is required for preview.")

    cv_data = dict(cv_data_override)
    _normalize_cv_data(cv_data)

    if template_id == "lebenslauf":
        lebenslauf_cache_key = f"lebenslauf_profile:{user_id}"
        cached_profile = await get_cached(lebenslauf_cache_key)
        if cached_profile:
            lp = json.loads(cached_profile)
        else:
            profile = await resume_tailor_service.get_profile_photo_fields(db, user_id)
            photo_base64 = ""
            safe_url = _safe_photo_url(profile.get("cv_photo_url"))
            if safe_url:
                try:
                    async with httpx.AsyncClient(timeout=8) as client:
                        r = await client.get(safe_url)
                        if r.status_code == 200:
                            photo_base64 = base64.b64encode(r.content).decode()
                except Exception:
                    pass
            lp = {
                "photo_base64": photo_base64 or None,
                "date_of_birth": profile.get("date_of_birth"),
                "nationality": profile.get("nationality"),
            }
            await set_cached(lebenslauf_cache_key, json.dumps(lp), ttl_seconds=3600)
        cv_data["photo_base64"] = lp["photo_base64"]
        cv_data["date_of_birth"] = lp["date_of_birth"]
        cv_data["nationality"] = lp["nationality"]
    else:
        cv_data.setdefault("photo_base64", None)
        cv_data.setdefault("date_of_birth", None)
        cv_data.setdefault("nationality", None)

    template_file = TEMPLATE_REGISTRY[template_id]["file"]
    tmpl = _jinja_env.get_template(template_file)
    html_out = tmpl.render(**cv_data)

    return HTMLResponse(content=html_out)
