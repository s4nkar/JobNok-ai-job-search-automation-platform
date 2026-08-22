"""Greenhouse ATS provider - public job-board API, no auth needed.

Fetches one company's board at a time - the caller (engine.py's
_fetch_source, driven by StartupHuntSource DB rows) supplies which company
via `source`.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.modules.startup_hunt.engine import (
    StartupHuntSourceConfig,
    _base_company_payload,
    _contacts_from_metadata,
    canonicalize_url,
    extract_domain,
    parse_dt,
)


def is_available() -> bool:
    return settings.startup_hunt_greenhouse_enabled


async def fetch(client: httpx.AsyncClient, source: StartupHuntSourceConfig) -> list[dict[str, Any]]:
    response = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{source.slug}/jobs")
    response.raise_for_status()
    payload = response.json()
    opportunities: list[dict[str, Any]] = []
    for item in payload.get("jobs", []):
        job_url = item.get("absolute_url")
        title = item.get("title")
        if not job_url or not title:
            continue
        company_payload = _base_company_payload(source)
        opportunities.append(
            {
                "opportunity_kind": "job",
                "company_name": source.company,
                "company_domain": extract_domain(company_payload.get("company_website_url")),
                "company_website_url": company_payload.get("company_website_url"),
                "company_careers_url": company_payload.get("company_careers_url"),
                "role_title": title,
                "location": ((item.get("location") or {}).get("name") or company_payload.get("city") or "Unspecified").strip(),
                "country": company_payload.get("country"),
                "source_name": source.name,
                "source_type": source.type,
                "direct_apply_url": job_url,
                "canonical_job_url": canonicalize_url(job_url),
                "portal_job_url": None,
                "posted_at": parse_dt(item.get("updated_at")),
                "company_payload": company_payload,
                "contacts": _contacts_from_metadata(source.metadata, source.company),
                "raw_text": f"{title} {source.company}",
                "citation": {
                    "source_name": source.name,
                    "canonical_url": canonicalize_url(job_url),
                    "job_url": job_url,
                    "posted_at": item.get("updated_at"),
                    "evidence": ["Fetched from configured greenhouse ATS feed"],
                    "extraction_note": "Direct ATS source used for freshest company-hosted apply link.",
                },
            }
        )
    return opportunities
