"""Salary research endpoint.

Streams the response via Server-Sent Events. Rate limited per user via
Upstash Redis.
"""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.services.cache import check_rate_limit
from app.core.security import get_user_id
from app.ai.llm import provider as ai_provider
from app.shared.utils import _rl_error
from app.modules.salary.schemas import SalaryResearchRequest

router = APIRouter()


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
