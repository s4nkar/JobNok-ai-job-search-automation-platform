"""Fallback job extraction for companies with no known ATS board
(ats_provider='generic', see ats_resolver.py) - PRD section 21. Looks for
schema.org/JobPosting JSON-LD on the careers page (common for SEO), which is
high-precision and requires no HTML-structure guessing. Freeform HTML
heuristic scraping is deliberately out of scope for MVP (high-maintenance,
unreliable yield) - a page with neither structured data nor a known ATS link
just yields zero jobs, and the sync worker marks the company 'no_jobs'.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from app.modules.startup_hunt.engine import canonicalize_url
from app.modules.startup_hunt.ingestion.ssrf_guard import SSRFBlockedError, safe_fetch
from app.modules.startup_hunt.models import CompanyRegistry

logger = logging.getLogger(__name__)

_JSON_LD_PATTERN = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S
)


def _extract_job_postings(html: str) -> list[dict[str, Any]]:
    postings: list[dict[str, Any]] = []
    for match in _JSON_LD_PATTERN.finditer(html):
        try:
            data = json.loads(match.group(1).strip())
        except (json.JSONDecodeError, AttributeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("@type") == "JobPosting":
                postings.append(candidate)
    return postings


def _location_text(posting: dict[str, Any]) -> tuple[str | None, str | None]:
    job_location = posting.get("jobLocation")
    entries = job_location if isinstance(job_location, list) else [job_location]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        address = entry.get("address") or {}
        if not isinstance(address, dict):
            continue
        locality = str(address.get("addressLocality") or "").strip()
        region = str(address.get("addressRegion") or "").strip()
        country = str(address.get("addressCountry") or "").strip() or None
        location = ", ".join(part for part in (locality, region) if part) or None
        if location or country:
            return location, country
    if posting.get("jobLocationType") == "TELECOMMUTE":
        return "Remote", None
    return None, None


def _to_opportunity(company: CompanyRegistry, posting: dict[str, Any]) -> dict[str, Any] | None:
    title = str(posting.get("title") or "").strip()
    if not title:
        return None

    apply_url = None
    application = posting.get("applicationContact")
    if isinstance(application, dict):
        apply_url = str(application.get("url") or "").strip() or None
    hiring_org_url = posting.get("url")
    apply_url = apply_url or (str(hiring_org_url).strip() if hiring_org_url else None) or company.career_url
    if not apply_url:
        return None

    location, country = _location_text(posting)
    description_raw = str(posting.get("description") or "")
    description_text = re.sub(r"<[^>]+>", " ", description_raw)
    description_text = re.sub(r"\s+", " ", description_text).strip() or None

    date_posted = str(posting.get("datePosted") or "").strip() or None
    posted_at: datetime | None = None
    if date_posted:
        try:
            posted_at = datetime.fromisoformat(date_posted.replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    canonical = canonicalize_url(apply_url)
    return {
        "opportunity_kind": "job",
        "company_name": company.name,
        "company_domain": None,
        "company_website_url": company.website_url,
        "company_careers_url": company.career_url,
        "role_title": title,
        "location": location or company.city or "Unspecified",
        "country": country or company.country,
        "source_name": "Generic career page",
        "source_type": "generic",
        "direct_apply_url": apply_url,
        "canonical_job_url": canonical,
        "portal_job_url": None,
        "posted_at": posted_at,
        "company_payload": {},
        "contacts": [],
        "raw_text": f"{title} {company.name} {location or ''} {description_text or ''}",
        "description_text": description_text,
        "citation": {
            "source_name": "Generic career page",
            "canonical_url": canonical,
            "job_url": apply_url,
            "posted_at": date_posted,
            "evidence": ["Extracted schema.org/JobPosting structured data from the company's careers page"],
            "extraction_note": "Fallback extraction - no known ATS board for this company.",
        },
    }


async def fetch(company: CompanyRegistry) -> list[dict[str, Any]]:
    if not company.career_url:
        return []
    try:
        html = await safe_fetch(company.career_url)
    except SSRFBlockedError:
        logger.warning("Generic crawler fetch blocked by SSRF guard for company %s", company.name)
        return []
    except Exception:
        logger.exception("Generic crawler fetch failed for company %s", company.name)
        return []

    postings = _extract_job_postings(html)
    return [op for posting in postings if (op := _to_opportunity(company, posting)) is not None]
