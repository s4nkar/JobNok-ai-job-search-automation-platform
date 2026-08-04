"""RapidAPI LinkedIn scraper — primary scraper.

Falls back to PhantomBuster if this returns no usable data.
"""

import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


async def scrape_linkedin_profile(profile_url: str) -> dict | None:
    """Scrape a LinkedIn profile via RapidAPI.

    Returns a dict with raw profile data, or None on failure.
    """
    if not settings.rapidapi_key:
        logger.warning("RapidAPI key is not configured")
        return None

    if not settings.rapidapi_linkedin_host:
        logger.warning("RapidAPI LinkedIn host is not configured")
        return None

    headers = {
        "x-rapidapi-key": settings.rapidapi_key,
        "x-rapidapi-host": settings.rapidapi_linkedin_host,
    }

    url = f"https://{settings.rapidapi_linkedin_host}/get-profile-data-by-url"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            res = await client.get(
                url,
                headers=headers,
                params={"url": profile_url},
            )

            logger.info(
                "RapidAPI LinkedIn response status=%s body=%s",
                res.status_code,
                res.text[:1000],
            )

            if res.status_code != 200:
                return None

            data = res.json()

            if not isinstance(data, dict):
                logger.warning("RapidAPI returned non-object JSON: %s", type(data))
                return None

            if isinstance(data.get("data"), dict):
                data = data["data"]

            if not isinstance(data, dict):
                logger.warning("RapidAPI returned non-object profile payload: %s", type(data))
                return None

            logger.info("RapidAPI profile payload keys=%s", list(data.keys()))

            name_candidates = [
                data.get("firstName"),
                data.get("first_name"),
                data.get("full_name"),
                data.get("fullName"),
                data.get("name"),
                data.get("full_name_with_middle_name"),
            ]

            if not any(name_candidates):
                logger.warning(
                    "RapidAPI returned no usable profile identity fields. Keys=%s payload=%s",
                    list(data.keys()),
                    str(data)[:1000],
                )
                return None

            return _normalize_rapidapi(data)

        except httpx.TimeoutException:
            logger.exception("RapidAPI LinkedIn request timed out")
            return None
        except httpx.RequestError:
            logger.exception("RapidAPI LinkedIn request failed")
            return None
        except Exception:
            logger.exception("RapidAPI LinkedIn parsing failed")
            return None


def _normalize_rapidapi(raw: dict) -> dict:
    """Normalize RapidAPI response to our internal schema."""
    first = raw.get("firstName", "") or raw.get("first_name", "")
    last = raw.get("lastName", "") or raw.get("last_name", "")

    name = (
        raw.get("full_name")
        or raw.get("fullName")
        or raw.get("name")
        or raw.get("full_name_with_middle_name")
        or f"{first} {last}".strip()
    )

    headline = (
        raw.get("headline")
        or raw.get("occupation")
        or raw.get("summaryHeadline")
        or ""
    )

    positions = []

    positions_obj = raw.get("positions")
    if isinstance(positions_obj, dict):
        positions = (
            positions_obj.get("positionHistory", [])
            or positions_obj.get("items", [])
        )
    elif isinstance(positions_obj, list):
        positions = positions_obj

    if not positions:
        experiences = raw.get("experiences") or raw.get("experience") or []
        if isinstance(experiences, list):
            positions = experiences

    current_position = positions[0] if positions and isinstance(positions[0], dict) else {}

    current_role = (
        current_position.get("title")
        or current_position.get("jobTitle")
        or raw.get("current_role")
        or raw.get("jobTitle")
        or ""
    )

    current_company = (
        current_position.get("companyName")
        or current_position.get("company")
        or current_position.get("company_name")
        or raw.get("current_company")
        or raw.get("company")
        or ""
    )

    skills_data = raw.get("skills", [])
    if isinstance(skills_data, dict):
        skills_data = skills_data.get("items", []) or skills_data.get("skills", [])

    if not isinstance(skills_data, list):
        skills_data = []

    skills = [
        s.get("name", "") if isinstance(s, dict) else s
        for s in skills_data[:20]
    ]

    educations_obj = raw.get("educations") or raw.get("education") or []
    if isinstance(educations_obj, dict):
        education_list = (
            educations_obj.get("educationHistory", [])
            or educations_obj.get("items", [])
        )
    elif isinstance(educations_obj, list):
        education_list = educations_obj
    else:
        education_list = []

    education = ""
    if education_list and isinstance(education_list[0], dict):
        ed = education_list[0]
        school = ed.get("schoolName") or ed.get("school") or ed.get("school_name") or ""
        degree = ed.get("degreeName") or ed.get("degree") or ""
        field = ed.get("fieldOfStudy") or ed.get("field") or ""
        education = f"{school} — {degree} {field}".strip(" —")

    return {
        "name": name,
        "headline": headline,
        "current_role": current_role,
        "current_company": current_company,
        "location": (
            raw.get("geoLocationName")
            or raw.get("location")
            or raw.get("geo")
            or ""
        ),
        "about": (
            raw.get("summary")
            or raw.get("about")
            or raw.get("description")
            or ""
        ),
        "recent_experience": _format_experience(positions[:3]),
        "skills": [s for s in skills if s],
        "education": education,
        "profile_url": (
            raw.get("profileURL")
            or raw.get("profileUrl")
            or raw.get("profile_url")
            or raw.get("linkedinUrl")
            or raw.get("linkedin_url")
            or ""
        ),
    }


def _format_experience(positions: list) -> str:
    parts = []

    for p in positions:
        if not isinstance(p, dict):
            continue

        title = p.get("title", "") or p.get("jobTitle", "")
        company = (
            p.get("companyName", "")
            or p.get("company", "")
            or p.get("company_name", "")
        )

        if title or company:
            parts.append(f"{title} at {company}".strip(" at"))

    return " | ".join(parts)