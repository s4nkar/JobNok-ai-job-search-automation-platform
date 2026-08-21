"""Adzuna provider - general job-board API, covers 17 countries."""

from __future__ import annotations

import logging
import math
import re
from typing import Any

import httpx

from app.core.config import settings
from app.modules.job_search.providers.base import ProviderError, canonicalize_job_url

logger = logging.getLogger(__name__)

# Adzuna's supported country path segments - https://developer.adzuna.com/
# Keep in sync with apps/web/app/(dashboard)/recent-job-search/page.tsx ADZUNA_COUNTRIES
_ADZUNA_COUNTRY_ALIASES: dict[str, str] = {
    "at": "at", "austria": "at",
    "au": "au", "australia": "au",
    "br": "br", "brazil": "br",
    "ca": "ca", "canada": "ca",
    "de": "de", "germany": "de", "deutschland": "de",
    "fr": "fr", "france": "fr",
    "gb": "gb", "uk": "gb", "united kingdom": "gb", "britain": "gb", "england": "gb",
    "in": "in", "india": "in",
    "it": "it", "italy": "it",
    "mx": "mx", "mexico": "mx",
    "nl": "nl", "netherlands": "nl", "holland": "nl",
    "nz": "nz", "new zealand": "nz",
    "pl": "pl", "poland": "pl",
    "ru": "ru", "russia": "ru",
    "sg": "sg", "singapore": "sg",
    "us": "us", "usa": "us", "united states": "us", "america": "us",
    "za": "za", "south africa": "za",
}

_FATAL_STATUSES = {401, 402, 403, 429}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def adzuna_country_code(country: str | None) -> str | None:
    """Map free text or a bare code to one of Adzuna's supported country segments."""
    if not country:
        return None
    return _ADZUNA_COUNTRY_ALIASES.get(_normalize_text(country))


def _classify_fatal(exc: Exception) -> str | None:
    """Return a plain-language, user-facing reason with no HTTP status codes
    or provider-internal details - those are logged separately for debugging."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in _FATAL_STATUSES:
            logger.warning("Adzuna returned HTTP %s: %s", status, exc.response.text[:500])
            if status == 401:
                return "Job search isn't configured correctly right now."
            if status == 402:
                return "Job search's usage limit was reached. Try again later."
            if status == 403:
                return "Job search declined the request. Try again shortly."
            if status == 429:
                return "Job search is rate-limited right now. Try again shortly."
    return None


def is_available() -> bool:
    return settings.job_search_adzuna_enabled and bool(settings.adzuna_app_id and settings.adzuna_app_key)


def supports_country(country: str | None, location: str | None) -> bool:
    return adzuna_country_code(country) is not None or adzuna_country_code(location) is not None


async def fetch(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch + normalize raw (unscored) results from Adzuna.

    Raises ProviderError for missing credentials / unsupported country
    (caller turns this into a clean 4xx if no other provider/cache has
    results). Fatal upstream errors (401/402/403/429) are caught and
    classified into a friendly message; anything else (timeout, DNS, 5xx)
    degrades to a generic "temporarily unavailable".
    """
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        raise ProviderError("Adzuna is not configured (missing app_id/app_key).")

    country_code = adzuna_country_code(payload.get("country")) or adzuna_country_code(payload.get("location"))
    if not country_code:
        raise ProviderError(
            "Could not determine an Adzuna-supported country from the search. "
            "Supported: " + ", ".join(sorted(set(_ADZUNA_COUNTRY_ALIASES.values())))
        )

    posted_within_hours = payload.get("posted_within_hours") or 720
    max_days_old = max(1, math.ceil(posted_within_hours / 24))
    result_limit = max(1, min(50, int(payload.get("result_limit", 10))))

    params = {
        "app_id": settings.adzuna_app_id,
        "app_key": settings.adzuna_app_key,
        "results_per_page": result_limit,
        "what": payload["query"],
        "max_days_old": max_days_old,
        "content-type": "application/json",
        # There is no parameter to get more than this - `/search` always caps
        # `description` at ~500 chars (Adzuna appends its own "…"), regardless
        # of what's requested here. Confirmed by testing: adding an invalid
        # "full_description" param made Adzuna reject the request outright
        # with a 400 for every query, not just fetch more text.
    }

    # Adzuna's `where` expects a city/region, not a country - the country is
    # already scoped via the /jobs/{country_code}/ URL segment. Passing the
    # country's own name as `where` (e.g. "Germany") makes Adzuna's location
    # resolver match nothing and silently return zero results, so only send
    # `where` when the location is actually more specific than the country.
    location = str(payload.get("location") or "").strip()
    if location and adzuna_country_code(location) != country_code:
        params["where"] = location

    url = f"{settings.adzuna_base_url}/jobs/{country_code}/search/1"

    async with httpx.AsyncClient(timeout=settings.job_search_timeout_seconds) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            friendly = _classify_fatal(exc)
            if not friendly:
                logger.warning("Adzuna returned HTTP %s: %s", exc.response.status_code, exc.response.text[:500])
            raise ProviderError(friendly or "Job search is temporarily unavailable.") from exc
        except httpx.HTTPError as exc:
            # Timeouts, connection resets, DNS failures, etc, not an HTTPStatusError
            # (no response was ever received), so it needs its own catch to degrade
            # the same way instead of surfacing as an unhandled 500.
            logger.warning("Adzuna request failed: %s", exc)
            raise ProviderError("Job search is temporarily unavailable.") from exc

    body = response.json()

    jobs: list[dict[str, Any]] = []
    for item in body.get("results", []):
        redirect_url = item.get("redirect_url")
        title = item.get("title")
        if not redirect_url or not title:
            continue
        company_name = ((item.get("company") or {}).get("display_name") or "Unknown company").strip()
        location_name = ((item.get("location") or {}).get("display_name") or "Unspecified").strip()
        category_label = (item.get("category") or {}).get("label")
        # Collapses runs of spaces/tabs within a line and excessive blank
        # lines, but keeps real paragraph breaks intact - a prior version
        # flattened everything (including newlines) into one run-on line,
        # which read as "stripped" once shown in full.
        raw_description = (item.get("description") or "").replace("\r\n", "\n").replace("\r", "\n")
        description = re.sub(r"[ \t]+", " ", raw_description)
        description = re.sub(r"\n{3,}", "\n\n", description).strip()

        jobs.append(
            {
                "source_name": "Adzuna",
                "provider_type": "adzuna",
                "external_job_id": str(item.get("id")) if item.get("id") is not None else None,
                "company": company_name,
                "role": title,
                "location": location_name,
                "job_url": redirect_url,
                "job_url_canonical": canonicalize_job_url(redirect_url),
                # Kept as an ISO string (not parsed to datetime) so this dict stays
                # JSON-serializable, needed for the Redis response cache.
                "posted_at": item.get("created"),
                "description_text": description,
                "metadata": {
                    "country": country_code,
                    "salary_min": item.get("salary_min"),
                    "salary_max": item.get("salary_max"),
                    "category": category_label,
                },
            }
        )
    return jobs
