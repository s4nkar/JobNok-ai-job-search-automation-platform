"""Interview prep endpoints — question generation and per-question regeneration.

Rate limited per user via Upstash Redis: a daily quota (generation and
regeneration split into separate buckets — see config.py's
rate_limit_interview_regenerate_per_day comment for why) plus a shared burst
window on both, same pattern as every other AI tool in this codebase.

generate_interview_questions returns a role_assessment (seniority, role
family, likely interview rounds, hedged company-reputation context) plus
the 10-question behavioral/situational set, and — only when the detected
role plausibly warrants them — a small set of DSA-style and system-design
prep questions with an "approach" guide rather than a full solution.

Generation auto-persists an InterviewPrepSession (see
service.py::resolve_session) rather than requiring an explicit Save click -
a forgotten click previously meant a full regeneration (AI cost + user
time) to recover lost content. The response includes "session_id" so the
frontend can keep referencing the same row across regenerate calls and a
reopen from My Docs.

Saved-session read/rename ("My Docs") lives in sessions_routes.py, included
into this module's router below.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.services.cache import acquire_lock, check_burst_limit, check_rate_limit, delete_cached
from app.shared.utils import _rl_error
from app.ai.llm import provider as ai_provider
from app.modules.interview_prep import service as interview_prep_service
from app.modules.interview_prep.prompts import INTERVIEW_SYSTEM_PROMPT, build_interview_prompt, build_regenerate_prompt
from app.modules.interview_prep.schemas import (
    InterviewPrepRequest,
    InterviewRegenerateRequest,
    validate_interview_response,
    validate_regenerate_response,
)
from app.modules.interview_prep.sessions_routes import router as sessions_router
from app.modules.interview_prep.text import strip_dashes_deep
from app.modules.usage.service import record_event as record_tool_usage

logger = logging.getLogger(__name__)
router = APIRouter()

router.include_router(sessions_router)

# A regenerate call only needs enough JD context to stay on-topic for one
# question's answer, not the full (up to 12,000-char) job description the
# main generation call uses — keeps this cheap, light-tier call's prompt
# small regardless of how long the original JD was.
_REGENERATE_JD_CONTEXT_CHARS = 1500

# Single-flight guard against two concurrent identical requests (double-
# click, a frontend retry loop, two tabs) each firing their own paid LLM
# call and - for /interview specifically - each independently resolving a
# session, which without this could create two rows for what was meant to
# be one submission. Burst limiting alone doesn't prevent this: it throttles
# RATE (N requests per window), not duplicate concurrent in-flight work.
# Released explicitly in a `finally` the moment this request's own work
# finishes (success, AI failure, or parse failure) via delete_cached, so a
# later LEGITIMATE request from the same user is never blocked longer than
# this one's own actual duration - the TTL below is only a safety ceiling
# for the (rare) case a process dies before reaching that `finally`.
_GENERATION_LOCK_TTL_SECONDS = 60


def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in response")
    return json.loads(text[start:end])


@router.post("/interview")
async def generate_interview_questions(
    request: Request, body: InterviewPrepRequest, db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    allowed, _ = await check_rate_limit(user_id, "interview", settings.rate_limit_interview_per_day)
    if not allowed:
        raise _rl_error("Interview Prep", settings.rate_limit_interview_per_day)
    try:
        burst_ok = await check_burst_limit(
            user_id, "interview", settings.rate_limit_burst_limit, settings.rate_limit_burst_window_seconds,
        )
    except Exception:
        burst_ok = True
    if not burst_ok:
        raise HTTPException(status_code=429, detail="Generating too quickly - please wait a few seconds and try again.")

    lock_key = f"interview_gen:{user_id}:lock"
    try:
        acquired = await acquire_lock(lock_key, _GENERATION_LOCK_TTL_SECONDS)
    except Exception:
        acquired = True  # fail open, same philosophy as every other limiter here
    if not acquired:
        raise HTTPException(
            status_code=429, detail="An interview prep kit is already being generated - please wait for it to finish.",
        )

    try:
        await record_tool_usage(db, user_id, "interview-prep")

        prompt = build_interview_prompt(body.job_description, company=body.company, role=body.role)

        try:
            # response_format=json_object structurally constrains the output to
            # valid JSON - a "return ONLY JSON" prompt instruction alone was
            # observed elsewhere in this codebase (resume_tailor, cover_letter)
            # not being reliably honored on its own. max_tokens=4000: the
            # response now covers role_assessment + 10 questions + up to 2 DSA +
            # up to 2 system-design items, each with its own answer/approach
            # text - noticeably larger than the old 10-questions-only payload.
            raw = await ai_provider.generate_text(
                prompt, INTERVIEW_SYSTEM_PROMPT, max_tokens=4000, tier="heavy",
                response_format={"type": "json_object"},
                reasoning_effort=settings.groq_reasoning_effort,
            )
        except ai_provider.AIGenerationError as exc:
            logger.warning("Interview prep generation failed: %r", exc)
            raise HTTPException(
                status_code=503, detail="AI service is temporarily unavailable. Please try again shortly.",
            ) from exc

        try:
            parsed = _extract_json(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("Interview prep: failed to parse LLM response as JSON (%r)", exc)
            raise HTTPException(status_code=500, detail="Failed to generate interview prep. Please try again.") from exc

        validated = validate_interview_response(parsed)
        sanitized = strip_dashes_deep(validated)

        session = await interview_prep_service.resolve_session(db, user_id, body, sanitized)
        return {**sanitized, "session_id": str(session.id)}
    finally:
        try:
            await delete_cached(lock_key)
        except Exception:
            pass


@router.post("/interview/regenerate")
async def regenerate_interview_answer(
    request: Request, body: InterviewRegenerateRequest, db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(request, db)
    allowed, _ = await check_rate_limit(
        user_id, "interview_regenerate", settings.rate_limit_interview_regenerate_per_day,
    )
    if not allowed:
        raise _rl_error("Interview Prep", settings.rate_limit_interview_regenerate_per_day)
    try:
        burst_ok = await check_burst_limit(
            user_id, "interview_regenerate", settings.rate_limit_burst_limit, settings.rate_limit_burst_window_seconds,
        )
    except Exception:
        burst_ok = True
    if not burst_ok:
        raise HTTPException(status_code=429, detail="Too many requests, please wait a few seconds and try again.")

    # Scoped by session_id+question_index, not just user_id - unlike the
    # main generate lock above, two DIFFERENT questions' regenerate calls
    # from the same user are entirely independent work and shouldn't block
    # each other; only a double-click on the SAME question's regenerate
    # button should be deduped.
    lock_key = f"interview_regen:{user_id}:{body.session_id}:{body.question_index}:lock"
    try:
        acquired = await acquire_lock(lock_key, _GENERATION_LOCK_TTL_SECONDS)
    except Exception:
        acquired = True
    if not acquired:
        raise HTTPException(status_code=429, detail="This answer is already being regenerated - please wait for it to finish.")

    try:
        prompt = build_regenerate_prompt(body.job_description[:_REGENERATE_JD_CONTEXT_CHARS], body.question)

        try:
            raw = await ai_provider.generate_text(
                prompt, max_tokens=500, tier="light",
                response_format={"type": "json_object"},
                reasoning_effort=settings.groq_reasoning_effort,
            )
        except ai_provider.AIGenerationError as exc:
            logger.warning("Interview answer regeneration failed: %r", exc)
            raise HTTPException(
                status_code=503, detail="AI service is temporarily unavailable. Please try again shortly.",
            ) from exc

        try:
            parsed = _extract_json(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("Interview regenerate: failed to parse LLM response as JSON (%r)", exc)
            raise HTTPException(status_code=500, detail="Failed to regenerate. Please try again.") from exc

        validated = validate_regenerate_response(parsed)
        sanitized = strip_dashes_deep(validated)

        if body.session_id is not None and body.question_index is not None:
            await interview_prep_service.apply_regenerated_answer(db, user_id, body.session_id, body.question_index, sanitized)

        return sanitized
    finally:
        try:
            await delete_cached(lock_key)
        except Exception:
            pass
