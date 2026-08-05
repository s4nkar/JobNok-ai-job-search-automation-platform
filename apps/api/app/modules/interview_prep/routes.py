"""Interview prep endpoints — question generation and per-question regeneration.

Rate limited per user via Upstash Redis (generation only; regeneration is
auth-gated but not separately rate limited).
"""

import json
from fastapi import APIRouter, Request, HTTPException

from app.core.config import settings
from app.services.cache import check_rate_limit
from app.core.security import get_user_id
from app.ai.llm import provider as ai_provider
from app.shared.utils import _rl_error
from app.modules.interview_prep.schemas import InterviewPrepRequest, InterviewRegenerateRequest

router = APIRouter()


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
