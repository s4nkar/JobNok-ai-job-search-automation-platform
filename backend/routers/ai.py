"""AI endpoints — resume tailor, cover letter, interview prep, salary research, CV generation.

All endpoints stream responses via Server-Sent Events.
Rate limits enforced per user per tool via Upstash Redis.
"""

import asyncio
import base64
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

import fitz  # PyMuPDF
import httpx
import numpy as np
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, Response
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML as WeasyHTML

from lib.config import settings
from lib.redis_client import check_rate_limit, get_cached, set_cached
from lib.resume_cache import (
    compute_resume_hash,
    deserialize_embeddings,
    get_resume_cache,
    serialize_embeddings,
    update_resume_cache,
)
from lib.resume_chunker import chunk_jd, chunk_resume, chunks_from_dicts, chunks_to_dicts, clean_jd_text
from lib.resume_matcher import match_resume_to_jd
from lib.embeddings import EmbeddingError, embed
from lib.supabase_client import get_supabase, get_user_id
from lib import ai_provider
from models.schemas import CoverLetterRequest, InterviewPrepRequest, InterviewRegenerateRequest, SalaryResearchRequest

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent / "lib" / "cv_templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=False)


def _rl_error(tool: str, limit: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=f"Daily limit of {limit} {tool} uses reached. Resets at midnight UTC."
    )


# ── Resume Tailor ─────────────────────────────────────────────────

@router.post("/tailor")
async def tailor_resume(
    request: Request,
    resume: UploadFile = File(...),
    job_description: str = Form(...),
):
    user_id = get_user_id(request)
    allowed, _ = await check_rate_limit(user_id, "resume", settings.rate_limit_resume_per_day)
    if not allowed:
        raise _rl_error("Resume Tailor", settings.rate_limit_resume_per_day)

    pdf_bytes = await resume.read()
    resume_hash = compute_resume_hash(pdf_bytes)

    # Cache hit: skip PyMuPDF re-parse. The cache survives 30 days, so subsequent
    # tailoring runs against new JDs reuse the extracted text for free.
    cached = await get_resume_cache(user_id, resume_hash)
    if cached and cached.get("text"):
        resume_text = cached["text"]
    else:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            resume_text = "\n".join(page.get_text() for page in doc)
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

    # ─── JD chunks + embeddings (always fresh) ────────────────────────
    jd_text_clean = clean_jd_text(job_description)
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
    ai_fields = await _generate_tailor_prose(resume_text, job_description, analysis)

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
    import numpy as np
    return np.zeros((0, 0), dtype="float32")


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

    system = """You are a CV tailoring assistant. The deterministic ATS analysis is already done —
you receive its results and must NOT recompute scores, matched keywords, or missing keywords.

Return ONLY valid JSON in this shape:
{
  "target_role": "<job title from the JD>",
  "target_company": "<company name from the JD>",
  "profile_headline": "<headline in the format: [target job title] | [relevant skill] | [relevant skill] | [relevant skill] — use the exact target job title from the JD as the first segment, then 2–3 skills from the resume most relevant to this specific role>",
  "tailored_summary": "<professional summary paragraph reframing genuine transferable experience honestly>",
  "bullet_rewrites": [{"original": "<EXACT original bullet from REWRITE CANDIDATES>", "improved": "<sharpened framing>"}],
  "summary": "<1-paragraph honest fit assessment noting strengths and real gaps>"
}

Hard rules:
- bullet_rewrites: ONLY rewrite bullets from the REWRITE CANDIDATES list. Use the original verbatim as the "original" field.
  * PRESERVE every number, percentage, and metric from the original
  * NEVER add tools, methods, or domains absent from the original
  * Adjust only verb / framing / emphasis — the evidence must stay identical
- profile_headline: lead with the exact job title from the JD, then 2–3 of the candidate's real skills most relevant to this role. Never add skills the resume doesn't show.
- tailored_summary: reframe genuine transferable experience honestly. Never claim domain expertise the resume does not show.
- summary: ground the fit assessment in the provided CRITICAL GAPS and TRANSFERABLE STRENGTHS.
- Return ONLY valid JSON, no markdown fences."""

    prompt = f"""DETERMINISTIC ANALYSIS (do not recompute, just use):
OVERALL SCORE: {analysis.overall_score}
SCORE BREAKDOWN: {json.dumps(analysis.score_breakdown)}
TRANSFERABLE STRENGTHS: {transferable_block}
CRITICAL GAPS (do not invent experience to cover these): {critical_block}

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


# ── CV PDF Generation ─────────────────────────────────────────────

@router.post("/tailor/generate-pdf")
async def generate_cv_pdf(request: Request, body: dict):
    user_id = get_user_id(request)

    template_id = body.get("template_id", "modern")
    if template_id not in ("modern", "classic"):
        raise HTTPException(status_code=422, detail="template_id must be 'modern' or 'classic'")

    resume_text = await get_cached(f"resume_text:{user_id}")
    if not resume_text:
        raise HTTPException(
            status_code=400,
            detail="No recent analysis found. Please run the Resume Tailor analysis first."
        )

    analysis = body.get("analysis") or {}
    bullet_rewrites = {r["original"]: r["improved"] for r in (analysis.get("bullet_rewrites") or [])}
    missing_kw = [m["keyword"] for m in (analysis.get("missing_keywords") or [])]

    # Fetch user profile
    sb = get_supabase()
    profile_res = await asyncio.to_thread(
        lambda: sb.table("profiles").select("*").eq("id", user_id).single().execute()
    )
    profile = profile_res.data or {}

    # Pull tailored fields from analysis (produced by /tailor endpoint)
    target_role = analysis.get("target_role") or ""
    target_company = analysis.get("target_company") or ""
    profile_headline = analysis.get("profile_headline") or ""
    tailored_summary = analysis.get("tailored_summary") or ""

    # Ask AI to structure the resume as JSON, applying rewrites
    system_struct = """You are a professional CV writer. Parse the resume text into a structured JSON object.

CRITICAL RULES — violating any of these produces a broken CV:
1. full_name: Extract the COMPLETE name (e.g. "Sankar Dev Santhosh", NOT just "Sankar"). Never truncate.
2. skills: For EVERY skill category, populate "items" as a non-empty comma-separated string of the actual tools/skills listed. NEVER leave "items" as null, empty string, or an empty list.
3. languages: Copy language entries EXACTLY as written in the resume. Do NOT substitute, add, or remove languages.
4. Completeness: Include ALL experience entries, ALL projects, ALL publications found in the resume. Do not omit any.
5. bullet_rewrites: Replace each original bullet with its improved version verbatim — do not skip any provided rewrite.
6. If a TAILORED HEADLINE is provided, use it as job_title. If a TAILORED SUMMARY is provided, use it as summary.

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
    {"category": "string", "items": "string — comma-separated list of actual skills, NEVER empty"}
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

    rewrites_block = "\n".join(f'  ORIGINAL: {o}\n  IMPROVED: {i}' for o, i in bullet_rewrites.items()) if bullet_rewrites else "None"
    kw_block = ", ".join(missing_kw) if missing_kw else "None"

    tailoring_block = ""
    if target_role or target_company:
        tailoring_block += f"\nTARGET ROLE: {target_role} at {target_company}"
    if profile_headline:
        tailoring_block += f"\nTAILORED HEADLINE TO USE AS job_title: {profile_headline}"
    if tailored_summary:
        tailoring_block += f"\nTAILORED SUMMARY TO USE AS summary: {tailored_summary}"

    prompt_struct = f"""Parse this resume into the required JSON format.
{tailoring_block}

BULLET REWRITES TO APPLY (replace originals with improved versions verbatim):
{rewrites_block}

MISSING KEYWORDS TO WEAVE IN WHERE NATURAL:
{kw_block}

RESUME TEXT:
{resume_text[:6000]}"""

    raw = await ai_provider.generate_text(prompt_struct, system_struct, max_tokens=4000)

    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        cv_data = json.loads(raw[start:end])
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to structure resume. Please try again.")

    # Post-process: strip skill rows with empty items (AI sometimes returns empty strings)
    if cv_data.get("skills"):
        cv_data["skills"] = [
            s for s in cv_data["skills"]
            if s.get("items") and str(s["items"]).strip()
        ]

    # Overlay profile contact fields (always authoritative for contact info)
    # full_name: only override if profile has a proper full name (first + last)
    profile_name = (profile.get("full_name") or "").strip()
    if profile_name and " " in profile_name:
        cv_data["full_name"] = profile_name

    # job_title/headline: analysis tailored headline wins; fall back to profile job_title
    if not profile_headline and profile.get("job_title"):
        cv_data["job_title"] = profile["job_title"]

    # cv_email takes priority over email parsed from resume
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

    # Classic template: fetch and embed profile photo as base64
    photo_base64 = None
    if template_id == "classic" and profile.get("cv_photo_url"):
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(profile["cv_photo_url"])
                if r.status_code == 200:
                    photo_base64 = base64.b64encode(r.content).decode()
        except Exception:
            pass

    # Add classic-specific fields from profile
    cv_data["photo_base64"] = photo_base64
    cv_data["date_of_birth"] = profile.get("date_of_birth")
    cv_data["nationality"] = profile.get("nationality")

    # Render template
    template_file = "template_classic.html" if template_id == "classic" else "template_modern.html"
    tmpl = _jinja_env.get_template(template_file)
    html_out = tmpl.render(**cv_data)

    # WeasyPrint → PDF (run in thread to avoid blocking event loop)
    pdf_bytes = await asyncio.to_thread(
        lambda: WeasyHTML(string=html_out).write_pdf()
    )

    # Optionally save artifact
    opportunity_id = body.get("opportunity_id")
    if opportunity_id:
        try:
            await asyncio.to_thread(
                lambda: sb.table("opportunity_artifacts").insert({
                    "user_id": user_id,
                    "opportunity_id": opportunity_id,
                    "artifact_type": "resume_analysis",
                    "tool_used": "resume-tailor",
                    "content": f"[Generated PDF — template: {template_id}]",
                    "metadata": {
                        "template_id": template_id,
                        "match_score": analysis.get("match_score"),
                    },
                }).execute()
            )
        except Exception:
            pass

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="tailored_cv_{template_id}.pdf"'},
    )


# ── Cover Letter ──────────────────────────────────────────────────

@router.post("/cover-letter")
async def generate_cover_letter(request: Request, body: CoverLetterRequest):
    user_id = get_user_id(request)
    allowed, _ = await check_rate_limit(user_id, "cover_letter", settings.rate_limit_cover_letter_per_day)
    if not allowed:
        raise _rl_error("Cover Letter Generator", settings.rate_limit_cover_letter_per_day)

    system = """You are a professional cover letter writer. Write compelling, personalized cover letters that:
- Open with a strong, specific hook (not "I am writing to apply for...")
- Highlight 2-3 specific accomplishments relevant to the role
- Show genuine enthusiasm for the company/role (not generic praise)
- End with a confident, action-oriented close
- Are 3-4 paragraphs, 250-350 words
- Avoid clichés: "passionate", "team player", "hard worker", "dynamic"

Output only the cover letter text, no subject line or extra commentary."""

    resume_section = f"\n\nMy resume summary:\n{body.resume_text}" if body.resume_text else ""

    prompt = f"""Write a cover letter for:
Company: {body.company}
Role: {body.role}
My key selling points: {body.selling_points}{resume_section}"""

    async def generate():
        async for chunk in ai_provider.stream_text(prompt, system, max_tokens=600):
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain")


# ── Interview Prep ────────────────────────────────────────────────

@router.post("/interview")
async def generate_interview_questions(request: Request, body: InterviewPrepRequest):
    user_id = get_user_id(request)
    allowed, _ = await check_rate_limit(user_id, "interview", settings.rate_limit_interview_per_day)
    if not allowed:
        raise _rl_error("Interview Prep", settings.rate_limit_interview_per_day)

    system = """You are an expert interview coach. Generate interview questions based on job descriptions.
Return exactly 10 questions as a JSON object:
{
  "questions": [
    {
      "question": <the interview question>,
      "framework": <"STAR" | "Behavioral" | "Technical" | "Situational">,
      "answer_framework": <2-3 sentence STAR-method answer guide tailored to THIS specific question>,
      "tips": [<2 specific tips for answering this question well>]
    }
  ]
}

Mix question types: 3 behavioral, 2 technical/role-specific, 2 situational, 2 motivational, 1 role-specific challenge.
Make questions specific to the role and company type, not generic.
Return ONLY valid JSON."""

    prompt = f"Generate 10 interview questions for this role:\n\n{body.job_description[:3000]}"

    text = await ai_provider.generate_text(prompt, system, max_tokens=3000)

    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        data = json.loads(text[start:end])
        return data
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to parse AI response. Please try again.")


@router.post("/interview/regenerate")
async def regenerate_interview_answer(request: Request, body: InterviewRegenerateRequest):
    get_user_id(request)  # auth check

    prompt = f"""Given this interview question and job context, provide a fresh STAR-method answer framework.

Job context: {body.job_description[:1000]}
Question: {body.question}

Return JSON:
{{
  "answer_framework": <fresh 2-3 sentence STAR guide>,
  "tips": [<2 specific tips>]
}}
Return ONLY valid JSON."""

    text = await ai_provider.generate_text(prompt, max_tokens=400)
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to regenerate. Please try again.")


# ── Salary Research ───────────────────────────────────────────────

@router.post("/salary")
async def research_salary(request: Request, body: SalaryResearchRequest):
    user_id = get_user_id(request)
    allowed, _ = await check_rate_limit(user_id, "salary", settings.rate_limit_salary_per_day)
    if not allowed:
        raise _rl_error("Salary Research", settings.rate_limit_salary_per_day)

    system = """You are a compensation research expert. Provide detailed, accurate salary information based on public data.
Structure your response with clear sections:

## Salary Range
Provide specific numbers with a realistic range.

## Median Salary
The market median for this role/location.

## Key Factors Affecting Compensation
List 4-5 factors (company size, industry, experience level, skills, etc.)

## Negotiation Talking Points
Provide 3-4 specific, actionable negotiation arguments.

## Data Context
Brief note on data sources and recency.

Be specific with numbers. Use USD unless the location suggests otherwise."""

    prompt = f"Research current market salary for: {body.job_title} in {body.location}"

    async def generate():
        async for chunk in ai_provider.stream_text(prompt, system, max_tokens=800):
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain")
