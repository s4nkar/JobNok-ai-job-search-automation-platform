"""Lever ATS provider - public job-board API, no auth needed."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.modules.startup_hunt.engine import (
    StartupHuntSourceConfig,
    _base_company_payload,
    _contacts_from_metadata,
    canonicalize_url,
    extract_domain,
)


def is_available() -> bool:
    return settings.startup_hunt_lever_enabled


async def fetch(client: httpx.AsyncClient, source: StartupHuntSourceConfig) -> list[dict[str, Any]]:
    response = await client.get(f"https://api.lever.co/v0/postings/{source.slug}?mode=json")
    response.raise_for_status()
    payload = response.json()
    opportunities: list[dict[str, Any]] = []
    for item in payload:
        job_url = item.get("hostedUrl")
        title = item.get("text")
        if not job_url or not title:
            continue
        categories = item.get("categories") or {}
        description_parts = []
        for block in item.get("lists", []) or []:
            content = block.get("content")
            if content:
                description_parts.append(re.sub(r"<[^>]+>", " ", content))
        description_text = re.sub(r"\s+", " ", " ".join(description_parts)).strip()
        company_payload = _base_company_payload(source)
        opportunities.append(
            {
                "opportunity_kind": "job",
                "company_name": source.company,
                "company_domain": extract_domain(company_payload.get("company_website_url")),
                "company_website_url": company_payload.get("company_website_url"),
                "company_careers_url": company_payload.get("company_careers_url"),
                "role_title": title,
                "location": (categories.get("location") or company_payload.get("city") or "Unspecified").strip(),
                "country": company_payload.get("country"),
                "source_name": source.name,
                "source_type": source.type,
                "direct_apply_url": job_url,
                "canonical_job_url": canonicalize_url(job_url),
                "portal_job_url": None,
                "posted_at": datetime.fromtimestamp(item.get("createdAt", 0) / 1000, tz=timezone.utc) if item.get("createdAt") else None,
                "company_payload": company_payload,
                "contacts": _contacts_from_metadata(source.metadata, source.company),
                "raw_text": f"{title} {source.company} {description_text}",
                "description_text": description_text or None,
                "citation": {
                    "source_name": source.name,
                    "canonical_url": canonicalize_url(job_url),
                    "job_url": job_url,
                    "posted_at": datetime.fromtimestamp(item.get("createdAt", 0) / 1000, tz=timezone.utc).isoformat() if item.get("createdAt") else None,
                    "evidence": ["Fetched from configured lever ATS feed"],
                    "extraction_note": "Direct ATS source used for startup-hosted role details and apply link.",
                },
            }
        )
    return opportunities
