"""LinkedIn scraping router — hybrid RapidAPI + PhantomBuster fallback + Redis cache."""

import json
from fastapi import APIRouter, Request, HTTPException

from app.core.config import settings
from app.core.security import get_user_id
from app.services.cache import check_rate_limit, get_cached, set_cached
from app.integrations import rapidapi, phantombuster
from app.ai.llm import provider as ai_provider
from app.modules.linkedin_fill.schemas import ScrapeLinkedInRequest, ScrapeLinkedInResponse

router = APIRouter()

CACHE_TTL = settings.linkedin_cache_ttl_days * 86400  # days → seconds


@router.post("/linkedin", response_model=ScrapeLinkedInResponse)
async def scrape_linkedin(request: Request, body: ScrapeLinkedInRequest):
    user_id = get_user_id(request)

    # ── Rate Limit ────────────────────────────────────────────────
    allowed, remaining = await check_rate_limit(
        user_id, "linkedin", settings.rate_limit_linkedin_per_day
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit of {settings.rate_limit_linkedin_per_day} LinkedIn scrapes reached. Resets at midnight UTC."
        )

    cache_key = f"linkedin:{body.linkedin_url}"

    # ── Cache Hit ─────────────────────────────────────────────────
    cached = await get_cached(cache_key)
    if cached:
        return ScrapeLinkedInResponse(data=json.loads(cached), cached=True)

    # ── Primary: RapidAPI ─────────────────────────────────────────
    profile = await rapidapi.scrape_linkedin_profile(body.linkedin_url)

    # ── Fallback: PhantomBuster ───────────────────────────────────
    if not profile:
        profile = await phantombuster.scrape_linkedin_profile(body.linkedin_url)

    if not profile:
        raise HTTPException(
            status_code=503,
            detail="Could not scrape the profile. It may be private or the scrapers are temporarily unavailable. Please try again."
        )

    # ── AI Enrichment ─────────────────────────────────────────────
    try:
        enriched = await _enrich_with_ai(profile)
        profile.update(enriched)
    except Exception:
        pass  # Enrichment is best-effort — return raw data on AI failure

    # ── Cache Result ──────────────────────────────────────────────
    await set_cached(cache_key, json.dumps(profile), CACHE_TTL)

    return ScrapeLinkedInResponse(data=profile, cached=False)


async def _enrich_with_ai(profile: dict) -> dict:
    """Use AI to generate personalized open-ended fields for template filling."""
    prompt = f"""Given this LinkedIn profile data, generate concise, personalized content for template auto-fill.

Profile:
- Name: {profile.get('name', '')}
- Headline: {profile.get('headline', '')}
- Current Role: {profile.get('current_role', '')} at {profile.get('current_company', '')}
- About: {profile.get('about', '')[:500]}
- Recent Experience: {profile.get('recent_experience', '')}

Generate a JSON object with these fields:
- personalized_intro: A 1-sentence personalized opener about their background (for cold outreach)
- key_strength: Their most notable professional strength based on profile (1 phrase)
- icebreaker: A specific, genuine observation about their work that could start a conversation

Return ONLY valid JSON, no markdown."""

    text = await ai_provider.generate_text(prompt, max_tokens=300)

    try:
        # Extract JSON from response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception:
        pass
    return {}
