"""Job search provider layer - Adzuna-backed general market search."""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.ai.llm import provider as ai_provider
from app.core.config import settings

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


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def canonicalize_job_url(url: str) -> str:
    parsed = urlparse(url)
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"gh_jid", "gh_src", "lever-source"}
    ]
    cleaned = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        query=urlencode(query_items),
        fragment="",
    )
    return urlunparse(cleaned)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _tokenize(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 1]


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


async def parse_preferences_prompt(prompt: str | None) -> dict[str, Any]:
    if not prompt or not prompt.strip():
        return {"keywords": [], "languages": [], "company_stage": None, "notes": []}

    system = """You extract structured job search preferences.
Return JSON only with this shape:
{
  "keywords": [string],
  "languages": [string],
  "company_stage": string | null,
  "notes": [string]
}
Keep values short and normalized."""

    try:
        text = await ai_provider.generate_text(prompt.strip(), system=system, max_tokens=250)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            return {
                "keywords": [str(v).strip().lower() for v in data.get("keywords", []) if str(v).strip()],
                "languages": [str(v).strip().lower() for v in data.get("languages", []) if str(v).strip()],
                "company_stage": (str(data.get("company_stage")).strip().lower() if data.get("company_stage") else None),
                "notes": [str(v).strip() for v in data.get("notes", []) if str(v).strip()],
            }
    except Exception:
        pass

    return {
        "keywords": _tokenize(prompt),
        "languages": ["english"] if "english" in prompt.lower() else [],
        "company_stage": None,
        "notes": [],
    }


class AdzunaConfigError(Exception):
    """Raised when Adzuna isn't configured or the country isn't supported."""


async def fetch_adzuna_raw(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch + normalize raw (unscored) results from Adzuna.

    Raises AdzunaConfigError for missing credentials / unsupported country
    (caller turns this into a clean 4xx). Fatal upstream errors (401/402/403/429)
    are caught and surfaced as an empty list with the caller expected to inspect
    logs - this mirrors startup_hunt's per-bucket fatal-error handling but there's
    only one provider here, so there's no "other buckets keep going" concern.
    """
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        raise AdzunaConfigError("Adzuna is not configured (missing app_id/app_key).")

    country_code = adzuna_country_code(payload.get("country")) or adzuna_country_code(payload.get("location"))
    if not country_code:
        raise AdzunaConfigError(
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
            raise AdzunaConfigError(friendly or "Job search is temporarily unavailable.") from exc
        except httpx.HTTPError as exc:
            # Timeouts, connection resets, DNS failures, etc, not an HTTPStatusError
            # (no response was ever received), so it needs its own catch to degrade
            # the same way instead of surfacing as an unhandled 500.
            logger.warning("Adzuna request failed: %s", exc)
            raise AdzunaConfigError("Job search is temporarily unavailable.") from exc

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
        description = re.sub(r"\s+", " ", (item.get("description") or "")).strip()

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


def score_all(
    raw_jobs: list[dict[str, Any]],
    payload: dict[str, Any],
    preferences: dict[str, Any],
    user_applications: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    scored = []
    for job in raw_jobs:
        enriched = _score_job(job, payload, preferences, user_applications)
        if enriched is not None:
            scored.append(enriched)
    return scored


def dedupe_and_rank(scored_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = _dedupe_jobs(scored_jobs)
    deduped.sort(key=lambda item: (-item["ranking"]["score"], item["ranking"]["age_hours"]))
    return deduped


def _score_job(
    job: dict[str, Any],
    payload: dict[str, Any],
    preferences: dict[str, Any],
    user_applications: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    query = payload["query"]
    location = payload["location"]
    country = (payload.get("country") or "").strip().lower()
    cutoff_hours = payload.get("posted_within_hours")
    remote_only = bool(payload.get("remote_only"))

    title_text = f'{job["role"]} {job["company"]} {job.get("description_text", "")}'
    query_tokens = _tokenize(query)
    if query_tokens and not any(token in _normalize_text(title_text) for token in query_tokens):
        return None

    location_text = _normalize_text(job["location"])
    location_requested = _normalize_text(location)
    metadata = job.get("metadata") or {}
    metadata_country = _normalize_text(str(metadata.get("country", "")))
    is_remote = "remote" in location_text or bool(metadata.get("remote"))

    if remote_only and not is_remote:
        return None

    if location_requested not in {"", "remote"} and location_requested not in location_text:
        if not (country and country == metadata_country):
            return None

    if country and country not in location_text and country != metadata_country:
        return None

    posted_at = _parse_dt(job.get("posted_at"))
    age_hours = 999999.0
    if posted_at:
        age_hours = max(0.0, (_now_utc() - posted_at).total_seconds() / 3600)
        if cutoff_hours is not None and age_hours > cutoff_hours:
            return None
    elif cutoff_hours is not None:
        return None

    preference_keywords = [kw for kw in preferences.get("keywords", []) if kw]
    preference_languages = [kw for kw in preferences.get("languages", []) if kw]
    company_stage = preferences.get("company_stage")

    evidence: list[str] = []
    score = 0.0

    token_hits = sum(1 for token in query_tokens if token in _normalize_text(title_text))
    score += token_hits * 4
    if token_hits:
        evidence.append(f"Matched role keywords: {', '.join(sorted(set(token for token in query_tokens if token in _normalize_text(title_text))))}")

    if location_requested and (location_requested in location_text or (location_requested == "remote" and is_remote)):
        score += 3
        evidence.append(f"Matched location filter: {payload['location']}")

    if is_remote:
        score += 1

    if posted_at:
        score += max(0.0, 48 - min(age_hours, 48)) / 6
        evidence.append(f"Posting appears recent: about {int(age_hours)} hours old")

    description_text = _normalize_text(job.get("description_text", ""))
    metadata_text = _normalize_text(json.dumps(metadata, default=str))
    matched_preference_keywords = [kw for kw in preference_keywords if kw in description_text or kw in metadata_text or kw in location_text]
    if matched_preference_keywords:
        score += len(matched_preference_keywords) * 2
        evidence.append(f"Matched preference keywords: {', '.join(matched_preference_keywords[:4])}")

    if preference_languages:
        source_languages = [_normalize_text(str(v)) for v in metadata.get("languages", [])] if isinstance(metadata.get("languages"), list) else []
        matched_languages = [lang for lang in preference_languages if lang in source_languages or lang in description_text]
        if matched_languages:
            score += len(matched_languages) * 1.5
            evidence.append(f"Matched language preference: {', '.join(matched_languages)}")

    if company_stage:
        source_stage = _normalize_text(str(metadata.get("stage", "")))
        if company_stage and company_stage in source_stage:
            score += 2
            evidence.append(f"Matched company stage: {metadata.get('stage')}")

    score += 2  # flat source-quality baseline (single provider, no cross-source weighting needed)

    canonical_url = job["job_url_canonical"]
    application = user_applications.get(canonical_url)

    citation = {
        "source_name": job["source_name"],
        "canonical_url": canonical_url,
        "job_url": job["job_url"],
        "posted_at": posted_at.isoformat() if posted_at else None,
        "evidence": evidence[:4] or ["Matched Adzuna listing"],
        "extraction_note": f"Fetched from {job['source_name']} and ranked against your filters.",
    }

    return {
        "source_name": job["source_name"],
        "provider_type": job["provider_type"],
        "external_job_id": job["external_job_id"],
        "company": job["company"],
        "role": job["role"],
        "location": job["location"],
        "job_url": job["job_url"],
        "job_url_canonical": canonical_url,
        "posted_at": posted_at.isoformat() if posted_at else None,
        "applied": bool(application and application.get("application_status") == "applied"),
        "application_status": application.get("application_status") if application else None,
        "tracked_application_id": application.get("id") if application else None,
        "citation": citation,
        "ranking": {"score": round(score, 3), "age_hours": age_hours},
    }


def _dedupe_jobs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        fingerprint = item["job_url_canonical"] or "|".join(
            [
                _normalize_text(item["company"]),
                _normalize_text(item["role"]),
                _normalize_text(item["location"]),
            ]
        )
        current = deduped.get(fingerprint)
        if current is None or item["ranking"]["score"] > current["ranking"]["score"]:
            deduped[fingerprint] = item
    return list(deduped.values())
