"""PhantomBuster fallback scraper.

Called automatically when RapidAPI fails or returns unusable data.
"""

import httpx
import asyncio
from lib.config import settings


PHANTOMBUSTER_API = "https://api.phantombuster.com/api/v2"


async def scrape_linkedin_profile(profile_url: str) -> dict | None:
    """Launch a PhantomBuster LinkedIn Profile Scraper agent and poll for results.

    Returns normalized profile dict or None on failure.
    """
    if not settings.phantombuster_api_key:
        return None

    headers = {"X-Phantombuster-Key": settings.phantombuster_api_key}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Launch the agent
            launch_res = await client.post(
                f"{PHANTOMBUSTER_API}/agents/launch",
                headers=headers,
                json={
                    "id": "your-phantombuster-agent-id",  # Configure in PhantomBuster dashboard
                    "argument": {"sessionCookie": "", "profileUrl": profile_url},
                },
            )
            if launch_res.status_code != 200:
                return None

            container_id = launch_res.json().get("containerId")
            if not container_id:
                return None

            # Poll for completion (max 25s)
            for _ in range(5):
                await asyncio.sleep(5)
                output_res = await client.get(
                    f"{PHANTOMBUSTER_API}/containers/fetch-output",
                    headers=headers,
                    params={"id": container_id},
                )
                output = output_res.json()
                if output.get("status") == "finished":
                    result_json = output.get("output", "[]")
                    import json
                    results = json.loads(result_json)
                    if results:
                        return _normalize_phantombuster(results[0])

            return None

        except (httpx.TimeoutException, httpx.RequestError, Exception):
            return None


def _normalize_phantombuster(raw: dict) -> dict:
    """Normalize PhantomBuster output to our internal schema."""
    return {
        "name": raw.get("fullName", ""),
        "headline": raw.get("headline", ""),
        "current_role": raw.get("jobTitle", ""),
        "current_company": raw.get("company", ""),
        "location": raw.get("location", ""),
        "about": raw.get("description", ""),
        "recent_experience": raw.get("jobs", ""),
        "skills": raw.get("skills", [])[:20],
        "education": raw.get("schools", ""),
        "profile_url": raw.get("profileUrl", ""),
    }
