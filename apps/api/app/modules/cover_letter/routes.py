"""Cover letter generation endpoint.

Streams the response via Server-Sent Events. Rate limited per user via
Upstash Redis.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.cache import check_rate_limit
from app.core.security import get_current_user_id
from app.ai.llm import provider as ai_provider
from app.shared.utils import _rl_error
from app.modules.cover_letter.schemas import CoverLetterRequest

router = APIRouter()


@router.post("/cover-letter")
async def generate_cover_letter(request: Request, body: CoverLetterRequest, db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(request, db)
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
