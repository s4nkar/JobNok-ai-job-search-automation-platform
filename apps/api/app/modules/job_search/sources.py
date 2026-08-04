"""Job search provider layer for direct ATS sources."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.ai.llm import provider as ai_provider
from app.core.config import settings


@dataclass
class SourceConfig:
    type: str
    name: str
    slug: str
    company: str
    metadata: dict[str, Any] = field(default_factory=dict)


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


def load_job_search_sources() -> list[SourceConfig]:
    try:
        raw = json.loads(settings.job_search_sources_json or "[]")
    except json.JSONDecodeError:
        return []

    sources: list[SourceConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        source_type = str(item.get("type", "")).strip().lower()
        slug = str(item.get("slug", "")).strip()
        name = str(item.get("name", "")).strip() or slug
        company = str(item.get("company", "")).strip() or name
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if source_type in {"greenhouse", "lever"} and slug and name:
            sources.append(SourceConfig(type=source_type, slug=slug, name=name, company=company, metadata=metadata))
    return sources


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


async def search_jobs(payload: dict[str, Any], user_applications: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sources = load_job_search_sources()
    preferences = await parse_preferences_prompt(payload.get("preferences_prompt"))

    if not sources:
        return [], preferences

    async with httpx.AsyncClient(timeout=settings.job_search_timeout_seconds, follow_redirects=True) as client:
        tasks = [_fetch_source(client, source) for source in sources]
        settled = await _gather(tasks)

    jobs: list[dict[str, Any]] = []
    for entries in settled:
        jobs.extend(entries)

    scored = []
    for job in jobs:
        enriched = _score_job(job, payload, preferences, user_applications)
        if enriched is not None:
            scored.append(enriched)

    deduped = _dedupe_jobs(scored)
    deduped.sort(key=lambda item: (-item["ranking"]["score"], item["ranking"]["age_hours"]))
    limit = payload.get("result_limit", 10)
    return deduped[:limit], preferences


async def _gather(tasks: list[Any]) -> list[list[dict[str, Any]]]:
    import asyncio

    settled = await asyncio.gather(*tasks, return_exceptions=True)
    results: list[list[dict[str, Any]]] = []
    for item in settled:
        if isinstance(item, Exception):
            results.append([])
        else:
            results.append(item)
    return results


async def _fetch_source(client: httpx.AsyncClient, source: SourceConfig) -> list[dict[str, Any]]:
    if source.type == "greenhouse":
        return await _fetch_greenhouse(client, source)
    if source.type == "lever":
        return await _fetch_lever(client, source)
    return []


async def _fetch_greenhouse(client: httpx.AsyncClient, source: SourceConfig) -> list[dict[str, Any]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{source.slug}/jobs"
    response = await client.get(url)
    response.raise_for_status()
    payload = response.json()

    jobs: list[dict[str, Any]] = []
    for item in payload.get("jobs", []):
        absolute_url = item.get("absolute_url")
        title = item.get("title")
        if not absolute_url or not title:
            continue
        jobs.append(
            {
                "source_name": source.name,
                "provider_type": source.type,
                "external_job_id": str(item.get("id")) if item.get("id") is not None else None,
                "company": source.company,
                "role": title,
                "location": ((item.get("location") or {}).get("name") or "Unspecified").strip(),
                "job_url": absolute_url,
                "job_url_canonical": canonicalize_job_url(absolute_url),
                "posted_at": _parse_dt(item.get("updated_at")),
                "description_text": "",
                "metadata": source.metadata,
            }
        )
    return jobs


async def _fetch_lever(client: httpx.AsyncClient, source: SourceConfig) -> list[dict[str, Any]]:
    url = f"https://api.lever.co/v0/postings/{source.slug}?mode=json"
    response = await client.get(url)
    response.raise_for_status()
    payload = response.json()

    jobs: list[dict[str, Any]] = []
    for item in payload:
        hosted_url = item.get("hostedUrl")
        title = item.get("text")
        if not hosted_url or not title:
            continue
        categories = item.get("categories") or {}
        description_parts = []
        for block in item.get("lists", []) or []:
            content = block.get("content")
            if content:
                description_parts.append(re.sub(r"<[^>]+>", " ", content))
        description = re.sub(r"\s+", " ", " ".join(description_parts)).strip()
        jobs.append(
            {
                "source_name": source.name,
                "provider_type": source.type,
                "external_job_id": str(item.get("id")) if item.get("id") is not None else None,
                "company": source.company,
                "role": title,
                "location": (categories.get("location") or "Unspecified").strip(),
                "job_url": hosted_url,
                "job_url_canonical": canonicalize_job_url(hosted_url),
                "posted_at": datetime.fromtimestamp(item.get("createdAt", 0) / 1000, tz=timezone.utc) if item.get("createdAt") else None,
                "description_text": description,
                "metadata": source.metadata,
            }
        )
    return jobs


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

    posted_at: datetime | None = job.get("posted_at")
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
    metadata_text = _normalize_text(json.dumps(metadata))
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

    source_quality = 2 if job["provider_type"] == "greenhouse" else 1.5
    score += source_quality

    canonical_url = job["job_url_canonical"]
    application = user_applications.get(canonical_url)

    citation = {
        "source_name": job["source_name"],
        "canonical_url": canonical_url,
        "job_url": job["job_url"],
        "posted_at": posted_at.isoformat() if posted_at else None,
        "evidence": evidence[:4] or ["Matched configured ATS source"],
        "extraction_note": f"Fetched from {job['provider_type']} ATS feed and ranked against your filters.",
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
