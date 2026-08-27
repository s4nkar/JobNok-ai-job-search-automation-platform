"""Google Programmable Search (CSE) web-discovery provider.

Deliberately CSE-only - the original inline version of this logic
(engine.py's now-untouched _fetch_web_search/_fetch_ats_discovery) falls
back to scraping a search engine's raw HTML results page when CSE isn't
configured. That fallback is not ported here: scraping a search engine's
SERP likely violates that engine's own ToS, and it's the kind of legal risk
this refactor is specifically trying to avoid carrying forward (see
providers/__init__.py's module docstring). Disabled by default - kept
around as a legitimate, ready-to-enable option once Google CSE credentials
are actually configured and wanted.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.modules.startup_hunt.engine import (
    StartupHuntSourceConfig,
    _build_web_query,
    _google_date_restrict,
    _infer_company_from_search_result,
    _role_title_from_search_result,
    _root_url,
    canonicalize_url,
    extract_domain,
    normalize_text,
)


def is_available() -> bool:
    return settings.startup_hunt_google_web_enabled and bool(settings.google_cse_api_key and settings.google_cse_cx)


async def fetch(
    client: httpx.AsyncClient,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    query = _build_web_query(payload, strategy)
    target = max(1, min(settings.startup_hunt_google_web_result_limit * 2, 50))

    raw_items: list[dict[str, Any]] = []
    start = 1
    while len(raw_items) < target and start <= 91:
        response = await client.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": settings.google_cse_api_key,
                "cx": settings.google_cse_cx,
                "q": query,
                "num": min(10, target - len(raw_items)),
                "start": start,
                "dateRestrict": _google_date_restrict(payload.get("posted_within_hours")),
            },
        )
        if response.status_code in (400, 429):
            break
        response.raise_for_status()
        data = response.json()
        page = data.get("items", []) or []
        if not page:
            break
        raw_items.extend(page)
        start += len(page)
        if len(page) < 10:
            break

    opportunities: list[dict[str, Any]] = []
    for item in raw_items:
        link = str(item.get("link", "")).strip()
        title = str(item.get("title", "")).strip()
        snippet = str(item.get("snippet", "")).strip()
        if not link or not title:
            continue

        company_name = _infer_company_from_search_result(title, link)
        role_title = _role_title_from_search_result(title, payload["query"])
        company_payload = {
            "stage": None,
            "company_size": None,
            "country": payload.get("country"),
            "city": payload.get("location"),
            "english_friendly": "english" in normalize_text(snippet),
            "ai_relevance": snippet,
            "relocation_support": "relocation" if "relocation" in normalize_text(snippet) else None,
            "company_website_url": _root_url(link),
            "company_careers_url": link if any(token in link.lower() for token in ["/careers", "/jobs", "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "smartrecruiters.com"]) else None,
            "source_tags": ["google-web"],
        }
        opportunities.append(
            {
                "opportunity_kind": "job" if company_payload["company_careers_url"] else "outreach_lead",
                "company_name": company_name,
                "company_domain": extract_domain(link),
                "company_website_url": company_payload["company_website_url"],
                "company_careers_url": company_payload["company_careers_url"],
                "role_title": role_title,
                "location": payload["location"],
                "country": payload.get("country"),
                "source_name": source.name,
                "source_type": source.type,
                "direct_apply_url": company_payload["company_careers_url"],
                "canonical_job_url": canonicalize_url(company_payload["company_careers_url"]) if company_payload["company_careers_url"] else None,
                "portal_job_url": link,
                "posted_at": None,
                "company_payload": company_payload,
                "contacts": [],
                "raw_text": f"{title} {snippet}",
                "citation": {
                    "source_name": source.name,
                    "canonical_url": canonicalize_url(link),
                    "job_url": link,
                    "posted_at": None,
                    "evidence": ["Discovered via Google Programmable Search"],
                    "extraction_note": "Web-discovered lead found through Google-based startup and job search.",
                },
            }
        )
    return opportunities
