"""AI endpoints — resume tailor, cover letter, interview prep, salary research.

All endpoints stream responses via Server-Sent Events.
Rate limits enforced per user per tool via Upstash Redis.
"""

import json
import fitz  # PyMuPDF
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from lib.config import settings
from lib.supabase_client import get_user_id
from lib.redis_client import check_rate_limit
from lib import ai_provider
from models.schemas import CoverLetterRequest, InterviewPrepRequest, InterviewRegenerateRequest, SalaryResearchRequest

router = APIRouter()


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

    # Extract text from PDF
    pdf_bytes = await resume.read()
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        resume_text = "\n".join(page.get_text() for page in doc)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse PDF. Ensure it's a valid PDF file.")

    system = """You are an expert ATS (Applicant Tracking System) analyst and resume coach.
Analyse the provided resume against the job description and return a JSON object with:
{
  "match_score": <integer 0-100, ATS keyword match percentage>,
  "matched_keywords": [<list of keywords found in both>],
  "missing_keywords": [{"keyword": <str>, "suggested_placement": <where to add it>}],
  "bullet_rewrites": [{"original": <original bullet>, "improved": <rewritten bullet>}],
  "summary": <1-paragraph honest assessment of fit>
}

Focus on:
- Technical skills and tools mentioned in JD vs resume
- Action verbs and quantified achievements
- ATS-friendly formatting
- Top 5 bullet rewrites maximum

Return ONLY valid JSON."""

    prompt = f"""RESUME:
{resume_text[:4000]}

JOB DESCRIPTION:
{job_description[:2000]}"""

    async def generate():
        full_text = ""
        async for chunk in ai_provider.stream_text(prompt, system, max_tokens=2000):
            full_text += chunk
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain")


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
    user_id = get_user_id(request)

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
