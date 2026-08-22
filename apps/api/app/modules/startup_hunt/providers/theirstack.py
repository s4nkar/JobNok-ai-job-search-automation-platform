"""TheirStack provider - paid Jobs API with funding-stage/company-size metadata."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.modules.startup_hunt.engine import (
    StartupHuntSourceConfig,
    _ai_engineer_family_variants,
    _country_code_for_indeed,
    _humanize_employee_count,
    _humanize_theirstack_stage,
    _looks_startup_focused,
    _safe_company_website_url,
    _theirstack_funding_stages,
    canonicalize_url,
    extract_domain,
    normalize_text,
    parse_dt,
)

# _theirstack_funding_stages/_humanize_theirstack_stage stay defined in
# engine.py rather than moving here - they're also used by the (untouched)
# Apify startup_jobs_intelligence code path, so engine.py remains their one
# source of truth and this file just imports them.


def is_available() -> bool:
    return settings.startup_hunt_theirstack_enabled and bool(settings.theirstack_api_key)


def _title_patterns(query: str) -> list[str]:
    return _ai_engineer_family_variants(query)[:6]


def _normalize_items(
    items: list[dict[str, Any]],
    source_name: str,
    source_type: str,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    normalize_limit = int(payload.get("theirstack_limit") or settings.startup_hunt_theirstack_result_limit)
    for item in items[:normalize_limit]:
        if not isinstance(item, dict):
            continue
        company_obj = item.get("company_object") if isinstance(item.get("company_object"), dict) else {}
        title = str(item.get("job_title") or item.get("title") or "").strip() or payload["query"]
        company_name = str(item.get("company_name") or company_obj.get("name") or "").strip() or "Unknown company"
        final_url = str(item.get("final_url") or item.get("url") or item.get("job_url") or "").strip()
        source_url = str(item.get("source_url") or final_url).strip()
        location = ", ".join([part for part in [item.get("city"), item.get("country")] if isinstance(part, str) and part.strip()]) or str(item.get("location") or payload["location"]).strip()
        company_website_url = _safe_company_website_url(
            company_obj.get("domain")
            or item.get("company_domain")
            or company_obj.get("url")
        )
        if company_website_url and not str(company_website_url).startswith("http"):
            company_website_url = f"https://{str(company_website_url).lstrip('/')}"
        company_careers_url = final_url or None
        description = str(item.get("description") or item.get("job_description") or "").strip()
        company_payload = {
            "stage": _humanize_theirstack_stage(company_obj.get("funding_stage")),
            "company_size": _humanize_employee_count(company_obj.get("employee_count")),
            "country": item.get("country") or payload.get("country"),
            "city": item.get("city") or payload.get("location"),
            "english_friendly": "english" in normalize_text(description) or "english" in normalize_text(title),
            "ai_relevance": description or title,
            "relocation_support": "relocation" if "relocation" in normalize_text(description) else None,
            "company_website_url": company_website_url,
            "company_careers_url": company_careers_url,
            "source_tags": ["theirstack", str(item.get("source") or "").strip()],
        }
        opportunities.append(
            {
                "opportunity_kind": "job",
                "company_name": company_name,
                "company_domain": extract_domain(company_website_url or company_careers_url or source_url),
                "company_website_url": company_website_url,
                "company_careers_url": company_careers_url,
                "role_title": title,
                "location": location,
                "country": item.get("country") or payload.get("country"),
                "source_name": source_name,
                "source_type": source_type,
                "direct_apply_url": company_careers_url,
                "canonical_job_url": canonicalize_url(company_careers_url or source_url) if (company_careers_url or source_url) else None,
                "portal_job_url": source_url or None,
                "posted_at": parse_dt(str(item.get("date_posted") or item.get("posted_at") or "")),
                "company_payload": company_payload,
                "contacts": [],
                "raw_text": f"{title} {company_name} {description}",
                "citation": {
                    "source_name": source_name,
                    "canonical_url": canonicalize_url(source_url) if source_url else "",
                    "job_url": company_careers_url or source_url,
                    "posted_at": item.get("date_posted") or item.get("posted_at"),
                    "evidence": ["Imported from TheirStack Jobs API"],
                    "extraction_note": "Result imported from TheirStack hiring search.",
                },
            }
        )
    return opportunities


async def fetch(
    client: httpx.AsyncClient,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    # payload.get("theirstack_limit") isn't a real request field anymore -
    # service.py's DB-first shortfall check writes a smaller override here
    # for one specific search when the DB cache already covers part of the
    # need (e.g. "only ask TheirStack for 6 more, not the full default 15").
    # Falls back to the server-config default otherwise. TheirStack's free
    # plan rejects the whole request (403, E-020) if `limit` exceeds its
    # page-size cap - clamp rather than let the entire bucket fail.
    result_limit = min(
        int(payload.get("theirstack_limit") or settings.startup_hunt_theirstack_result_limit),
        settings.theirstack_max_page_size,
    )
    request_payload: dict[str, Any] = {
        "limit": result_limit,
        "page": 0,
        "posted_at_max_age_days": max(1, int((payload.get("posted_within_hours") or 168) / 24)),
        "job_title_pattern_or": _title_patterns(payload["query"]),
        "job_country_code_or": [_country_code_for_indeed(payload.get("country")).upper()],
        "company_country_code_or": [_country_code_for_indeed(payload.get("country")).upper()],
    }

    if payload.get("remote_only"):
        request_payload["remote"] = True

    if _looks_startup_focused(payload, strategy):
        request_payload["max_employee_count_or_null"] = 1000
        explicit_stage = normalize_text(str(payload.get("company_stage") or strategy.get("company_stage") or ""))
        if explicit_stage:
            funding_stages = _theirstack_funding_stages(payload, strategy)
            if funding_stages:
                request_payload["funding_stage_or"] = funding_stages

    response = await client.post(
        f"{settings.theirstack_base_url.rstrip('/')}/v1/jobs/search",
        headers={
            "Authorization": f"Bearer {settings.theirstack_api_key}",
            "Content-Type": "application/json",
        },
        json=request_payload,
    )
    response.raise_for_status()
    data = response.json()
    items = data if isinstance(data, list) else data.get("data") or data.get("jobs") or data.get("results") or []
    return _normalize_items(items, source.name, source.type, payload)
