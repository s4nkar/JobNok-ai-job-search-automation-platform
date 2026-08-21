"""Arbeitnow provider - free, keyless job board API.

No server-side search at all - confirmed live, the only documented param is
`?page=` for pagination, and it returns the ~175 most recent postings across
every category, sorted by created_at. There's nothing to filter by keyword,
location, or remote here; we fetch page 1 and let scoring.score_all do all
the matching against our own filters, exactly as it already does for
DB-cached candidates.

Arbeitnow's own API terms ask not to abuse it ("please do not abuse... no
documented rate limit) and their data only refreshes hourly, so page 1 is
cached briefly - N different search queries within that window share one
fetch instead of each triggering their own.
"""

from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.modules.job_search.providers.base import ProviderError, canonicalize_job_url
from app.services.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

_URL = "https://www.arbeitnow.com/api/job-board-api"
_CACHE_KEY = "job_search:provider:arbeitnow:page1"
_CACHE_TTL_SECONDS = 1800

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def is_available() -> bool:
    return settings.job_search_arbeitnow_enabled


def supports_country(country: str | None, location: str | None) -> bool:
    # No country field in Arbeitnow's data at all - always applicable, and
    # scoring's own location-text matching filters out anything irrelevant
    # after fetch, same as it does for every other provider's candidates.
    return True


def _html_to_text(raw: str) -> str:
    """Arbeitnow's `description` is HTML-escaped HTML (literal `&lt;p&gt;`
    for `<p>`), not plain text like Adzuna's - unescape, strip tags, then
    apply the same whitespace cleanup Adzuna's description gets."""
    unescaped = html.unescape(raw)
    text = _TAG_RE.sub(" ", unescaped)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


async def _fetch_page_1() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=settings.job_search_timeout_seconds) as client:
        try:
            response = await client.get(_URL)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("Arbeitnow returned HTTP %s: %s", exc.response.status_code, exc.response.text[:500])
            raise ProviderError("Job search (Arbeitnow) is temporarily unavailable.") from exc
        except httpx.HTTPError as exc:
            logger.warning("Arbeitnow request failed: %s", exc)
            raise ProviderError("Job search (Arbeitnow) is temporarily unavailable.") from exc
    return response.json().get("data", [])


async def fetch(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not is_available():
        raise ProviderError("Arbeitnow search is turned off.")

    items: list[dict[str, Any]] | None = None
    try:
        cached = await get_cached(_CACHE_KEY)
        if cached:
            items = json.loads(cached)
    except Exception:
        items = None

    if items is None:
        items = await _fetch_page_1()
        try:
            await set_cached(_CACHE_KEY, json.dumps(items), _CACHE_TTL_SECONDS)
        except Exception:
            pass

    jobs: list[dict[str, Any]] = []
    for item in items:
        slug = item.get("slug")
        title = item.get("title")
        job_url = item.get("url")
        if not slug or not title or not job_url:
            continue

        company_name = (item.get("company_name") or "Unknown company").strip()
        is_remote = bool(item.get("remote"))
        location_name = (item.get("location") or "").strip() or ("Remote" if is_remote else "Unspecified")

        created_at = item.get("created_at")
        posted_at = datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat() if created_at else None

        tags = item.get("tags") or []

        jobs.append(
            {
                "source_name": "Arbeitnow",
                "provider_type": "arbeitnow",
                "external_job_id": slug,
                "company": company_name,
                "role": title,
                "location": location_name,
                "job_url": job_url,
                "job_url_canonical": canonicalize_job_url(job_url),
                "posted_at": posted_at,
                "description_text": _html_to_text(item.get("description") or ""),
                "metadata": {
                    "country": None,
                    "salary_min": None,
                    "salary_max": None,
                    "category": tags[0] if tags else None,
                    "remote": is_remote,
                },
            }
        )
    return jobs
