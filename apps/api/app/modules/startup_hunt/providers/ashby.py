"""Ashby ATS provider - public job-board API, no auth needed.

The original inline version of this fetch (engine.py) fell back to scraping
a company's own careers page (_fetch_startup_company) on a 404. Dropped
here deliberately - that fallback couples this provider to the crawler
bucket's scraping logic, which isn't part of this refactor (see
providers/__init__.py's module docstring). A 404 here now just means no
Ashby board found for that company - same as greenhouse/lever's behavior
when their APIs don't have a matching board either.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.modules.startup_hunt.engine import (
    StartupHuntSourceConfig,
    _base_company_payload,
    _contacts_from_metadata,
    canonicalize_url,
    extract_domain,
    normalize_text,
    parse_dt,
)


def is_available() -> bool:
    return settings.startup_hunt_ashby_enabled


def _board_name(source: StartupHuntSourceConfig) -> str | None:
    if source.slug:
        return source.slug.strip()
    if not source.url:
        return None
    parsed = urlparse(source.url)
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    return parts[-1].strip() or None


def _location(item: dict[str, Any]) -> str | None:
    location = str(item.get("location") or "").strip()
    if location:
        return location
    address = (((item.get("address") or {}).get("postalAddress")) or {}) if isinstance(item.get("address"), dict) else {}
    locality = str(address.get("addressLocality") or "").strip()
    region = str(address.get("addressRegion") or "").strip()
    country = str(address.get("addressCountry") or "").strip()
    parts = [part for part in [locality, region, country] if part]
    if parts:
        return ", ".join(parts)
    return None


def _country(item: dict[str, Any]) -> str | None:
    address = (((item.get("address") or {}).get("postalAddress")) or {}) if isinstance(item.get("address"), dict) else {}
    country = str(address.get("addressCountry") or "").strip()
    if country:
        return country
    secondary = item.get("secondaryLocations") or []
    if isinstance(secondary, list):
        for entry in secondary:
            if not isinstance(entry, dict):
                continue
            sec_address = entry.get("address") or {}
            country = str(sec_address.get("addressCountry") or "").strip()
            if country:
                return country
    return None


async def fetch(client: httpx.AsyncClient, source: StartupHuntSourceConfig) -> list[dict[str, Any]]:
    board_name = _board_name(source)
    if not board_name:
        return []

    response = await client.get(
        f"https://api.ashbyhq.com/posting-api/job-board/{board_name}",
        params={"includeCompensation": "true"},
    )
    response.raise_for_status()
    payload = response.json()
    opportunities: list[dict[str, Any]] = []
    company_payload = _base_company_payload(source)
    company_payload["company_careers_url"] = company_payload.get("company_careers_url") or source.url or f"https://jobs.ashbyhq.com/{board_name}"

    for item in payload.get("jobs", []) or []:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        direct_apply_url = str(item.get("applyUrl") or "").strip() or None
        job_url = str(item.get("jobUrl") or "").strip() or direct_apply_url
        if not job_url and not direct_apply_url:
            continue

        description = str(item.get("descriptionPlain") or "").strip()
        location = _location(item) or company_payload.get("city") or "Unspecified"
        opportunities.append(
            {
                "opportunity_kind": "job",
                "company_name": source.company,
                "company_domain": extract_domain(company_payload.get("company_website_url") or company_payload.get("company_careers_url")),
                "company_website_url": company_payload.get("company_website_url"),
                "company_careers_url": company_payload.get("company_careers_url"),
                "role_title": title,
                "location": location,
                "country": _country(item) or company_payload.get("country"),
                "source_name": source.name,
                "source_type": source.type,
                "direct_apply_url": direct_apply_url or job_url,
                "canonical_job_url": canonicalize_url(job_url or direct_apply_url or company_payload["company_careers_url"]),
                "portal_job_url": job_url,
                "posted_at": parse_dt(str(item.get("publishedAt") or "")),
                "company_payload": {
                    **company_payload,
                    "source_tags": [
                        *company_payload.get("source_tags", []),
                        *[
                            value
                            for value in [
                                str(item.get("department") or "").strip() or None,
                                str(item.get("team") or "").strip() or None,
                                str(item.get("employmentType") or "").strip() or None,
                                str(item.get("workplaceType") or "").strip() or None,
                            ]
                            if value
                        ],
                    ],
                    "english_friendly": bool(company_payload.get("english_friendly")) or "english" in normalize_text(description),
                },
                "contacts": _contacts_from_metadata(source.metadata, source.company),
                "raw_text": f"{title} {source.company} {location} {description}",
                "citation": {
                    "source_name": source.name,
                    "canonical_url": canonicalize_url(job_url or direct_apply_url or company_payload["company_careers_url"]),
                    "job_url": direct_apply_url or job_url or company_payload["company_careers_url"],
                    "posted_at": item.get("publishedAt"),
                    "evidence": ["Fetched from configured Ashby job board"],
                    "extraction_note": "Direct Ashby job board source used for current public startup roles.",
                },
            }
        )
    return opportunities
