"""RapidAPI LinkedIn scraper — primary scraper.

Falls back to PhantomBuster if this returns no usable data.
"""

import httpx
from lib.config import settings


async def scrape_linkedin_profile(profile_url: str) -> dict | None:
    """Scrape a LinkedIn profile via RapidAPI.

    Returns a dict with raw profile data, or None on failure.
    """
    if not settings.rapidapi_key:
        return None

    # Normalize the URL to extract the username
    username = profile_url.rstrip("/").split("/in/")[-1].split("/")[0]

    headers = {
        "x-rapidapi-key": settings.rapidapi_key,
        "x-rapidapi-host": settings.rapidapi_linkedin_host,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            res = await client.get(
                f"https://{settings.rapidapi_linkedin_host}/get-profile-data-by-url",
                headers=headers,
                params={"url": profile_url},
            )
            if res.status_code != 200:
                return None

            data = res.json()

            # Validate minimum usable data
            if not data.get("firstName") and not data.get("full_name") and not data.get("name"):
                return None

            return _normalize_rapidapi(data)

        except (httpx.TimeoutException, httpx.RequestError):
            return None


def _normalize_rapidapi(raw: dict) -> dict:
    """Normalize RapidAPI response to our internal schema."""
    first = raw.get("firstName", "")
    last = raw.get("lastName", "")
    name = raw.get("full_name") or raw.get("name") or f"{first} {last}".strip()

    positions = raw.get("positions", {}).get("positionHistory", [])
    current_position = positions[0] if positions else {}

    skills_data = raw.get("skills", [])
    skills = [s.get("name", s) if isinstance(s, dict) else s for s in skills_data[:20]]

    education_list = raw.get("educations", {}).get("educationHistory", [])
    education = ""
    if education_list:
        ed = education_list[0]
        education = f"{ed.get('schoolName', '')} — {ed.get('degreeName', '')} {ed.get('fieldOfStudy', '')}".strip(" —")

    return {
        "name": name,
        "headline": raw.get("headline", ""),
        "current_role": current_position.get("title", ""),
        "current_company": current_position.get("companyName", ""),
        "location": raw.get("geoLocationName", "") or raw.get("location", ""),
        "about": raw.get("summary", ""),
        "recent_experience": _format_experience(positions[:3]),
        "skills": skills,
        "education": education,
        "profile_url": raw.get("profileURL", ""),
    }


def _format_experience(positions: list) -> str:
    parts = []
    for p in positions:
        title = p.get("title", "")
        company = p.get("companyName", "")
        if title or company:
            parts.append(f"{title} at {company}".strip(" at"))
    return " | ".join(parts)
