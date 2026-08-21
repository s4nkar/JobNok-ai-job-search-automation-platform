"""Bundesagentur für Arbeit (German Federal Employment Agency) provider.

Unofficial API - there's no real developer registration; `X-API-Key:
jobboerse-jobsuche` is a static key reverse-engineered from the agency's own
mobile app and shared by the community (github.com/bundesAPI/jobsuche-api).
It could change or break without notice - settings.job_search_bundesagentur_enabled
exists specifically so it can be turned off with an env var, not a deploy.

Germany-only. The search endpoint doesn't return a description or salary
(those live behind a second per-job /jobdetails call, deliberately skipped
here to avoid up to result_limit extra requests per search against an API
with no documented rate limit) - so these listings carry an empty
description and no salary, both already handled as optional everywhere else
this data can be missing.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import httpx

from app.core.config import settings
from app.modules.job_search.providers.base import ProviderError, canonicalize_job_url

logger = logging.getLogger(__name__)

_BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
# v4/app/jobs (the endpoint the community example client uses) returns a bare
# 403 with these headers - confirmed live. v6/jobs is the one that actually
# works and returns real data; different response shape entirely (see the
# field names below), not just a version bump.
_SEARCH_PATH = "/pc/v6/jobs"
# Not a real secret - it's the same key the official Bundesagentur mobile app
# ships with, publicly known and not ours to rotate, unlike adzuna_app_id/
# app_key below which are our own credentials and belong in settings.
_API_KEY = "jobboerse-jobsuche"
# The API gates on this (a generic httpx User-Agent gets a bare 403) - matches
# the mobile app's own header, per the community example client.
_USER_AGENT = "Jobsuche/2.9.2 (de.arbeitsagentur.jobboerse; build:1077; iOS 15.1.0)"

_GERMANY_ALIASES = {"de", "germany", "deutschland"}


def is_available() -> bool:
    return settings.job_search_bundesagentur_enabled


def supports_country(country: str | None, location: str | None) -> bool:
    for value in (country, location):
        if value and value.strip().lower() in _GERMANY_ALIASES:
            return True
    return False


def _job_detail_url(refnr: str) -> str:
    return f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"


async def fetch(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch + normalize raw (unscored) results from Bundesagentur für Arbeit."""
    if not is_available():
        raise ProviderError("Bundesagentur für Arbeit search is turned off.")

    posted_within_hours = payload.get("posted_within_hours") or 720
    days_since_published = max(0, min(100, math.ceil(posted_within_hours / 24)))
    result_limit = max(1, min(50, int(payload.get("result_limit", 10))))

    params: dict[str, Any] = {
        "was": payload["query"],
        "size": result_limit,
        "page": 1,
        "veroeffentlichtseit": days_since_published,
        # 1 = regular employment - excludes training/internship/self-employment
        # postings, matching this tool's general "recent job" intent.
        "angebotsart": 1,
    }
    location = str(payload.get("location") or "").strip()
    if location and location.lower() not in _GERMANY_ALIASES:
        params["wo"] = location

    headers = {"X-API-Key": _API_KEY, "User-Agent": _USER_AGENT}

    async with httpx.AsyncClient(timeout=settings.job_search_timeout_seconds) as client:
        try:
            response = await client.get(f"{_BASE_URL}{_SEARCH_PATH}", params=params, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("Bundesagentur returned HTTP %s: %s", exc.response.status_code, exc.response.text[:500])
            raise ProviderError("Job search (Bundesagentur für Arbeit) is temporarily unavailable.") from exc
        except httpx.HTTPError as exc:
            logger.warning("Bundesagentur request failed: %s", exc)
            raise ProviderError("Job search (Bundesagentur für Arbeit) is temporarily unavailable.") from exc

    body = response.json()

    jobs: list[dict[str, Any]] = []
    for item in body.get("ergebnisliste", []):
        refnr = item.get("referenznummer")
        title = item.get("stellenangebotsTitel")
        if not refnr or not title:
            continue

        company_name = (item.get("firma") or "Unknown company").strip()
        # An array (stellenlokationen), not a single object - a posting can
        # have multiple sites; the first is representative enough for search
        # display, same granularity Adzuna's single `location` field gives.
        locations = item.get("stellenlokationen") or []
        adresse = (locations[0].get("adresse") or {}) if locations else {}
        location_parts = [p for p in [adresse.get("ort"), adresse.get("region")] if p]
        location_name = ", ".join(location_parts) or "Unspecified"

        # externeUrl is only present when the listing originates from an
        # external site - confirmed live that most/all Bundesagentur-native
        # postings don't have one, so fall back to the agency's own public
        # job-detail page (which always exists, keyed by referenznummer).
        job_url = item.get("externeUrl") or _job_detail_url(refnr)

        jobs.append(
            {
                "source_name": "Bundesagentur für Arbeit",
                "provider_type": "bundesagentur",
                "external_job_id": refnr,
                "company": company_name,
                "role": title,
                "location": location_name,
                "job_url": job_url,
                "job_url_canonical": canonicalize_job_url(job_url),
                "posted_at": item.get("datumErsteVeroeffentlichung"),
                "description_text": "",
                "metadata": {
                    "country": "de",
                    "salary_min": None,
                    "salary_max": None,
                    "category": None,
                },
            }
        )
    return jobs
