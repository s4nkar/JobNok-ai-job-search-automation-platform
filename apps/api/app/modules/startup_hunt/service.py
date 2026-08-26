"""Startup Hunt business logic, SQLAlchemy-backed.

This module intentionally does not write into tracker's job_applications
table - startup_hunt_opportunities is its own tracked list, surfaced in the
Tracker's dedicated "Startup Leads" tab, so a lead marked "applied" here shows
up exactly once instead of also duplicating into the Tracker's manual
Applications tab.
"""

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from arq.connections import ArqRedis
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.cache import acquire_lock, get_cached, jittered_ttl, set_cached
from app.shared.repository import UserScopedRepository
from app.shared.utils import row_to_dict
from app.modules.job_search.models import Job, query_job_cache_candidates, touch_job_cache_rows
from app.modules.job_search.service import _upsert_jobs_cache
from app.modules.job_search.providers.adzuna import adzuna_country_code
from app.modules.startup_hunt import resolver
from app.modules.startup_hunt.engine import (
    StartupHuntSourceConfig,
    _dedupe_opportunities,
    _score_opportunity,
    build_seeded_sources,
    canonicalize_url,
    extract_domain,
    parse_strategy_prompt,
    search_startup_hunt,
    tokenize,
)
from app.modules.startup_hunt.models import (
    CompanyRegistry,
    OpportunityArtifact,
    StartupHuntCompany,
    StartupHuntContact,
    StartupHuntOpportunity,
    StartupHuntSource,
)
from app.modules.startup_hunt.schemas import (
    StartupHuntOpportunityCreateRequest,
    StartupHuntOpportunityUpdateRequest,
    StartupHuntSourceIn,
)


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class OpportunityRepository(UserScopedRepository[StartupHuntOpportunity]):
    model = StartupHuntOpportunity


async def _load_opportunities(db: AsyncSession, user_id: str) -> list[StartupHuntOpportunity]:
    rows = (
        await db.execute(select(StartupHuntOpportunity).where(StartupHuntOpportunity.user_id == user_id))
    ).scalars().all()
    return list(rows)


def _opportunity_lookup_key(data: dict[str, Any]) -> str:
    """Same fallback-to-composite-key logic used for matching a result item
    back to a user's own saved opportunity, shared between
    _load_opportunity_map (building the lookup table) and
    _reattach_saved_state (looking a cached result item up in it) so both
    sides always build the key the same way."""
    return data.get("canonical_job_url") or (
        f'{(data.get("company_name") or "").strip().lower()}|'
        f'{(data.get("role_title") or "").strip().lower()}|'
        f'{(data.get("location") or "").strip().lower()}'
    )


async def _load_opportunity_map(db: AsyncSession, user_id: str) -> dict[str, dict]:
    opportunities = await _load_opportunities(db, user_id)
    dicts = [row_to_dict(row) for row in opportunities]
    return {_opportunity_lookup_key(d): d for d in dicts}


def _job_row_to_opportunity_dict(row: Job) -> dict[str, Any]:
    """Map a shared `jobs` cache row into Startup Hunt's opportunity dict shape
    so the existing `_score_opportunity` can run on it unchanged. Used for
    both the theirstack DB-shortfall check and the ATS (greenhouse/lever/
    ashby) DB-first cache-first check - row.source tells us which.

    No company_payload/contacts enrichment survives a cache round-trip — the
    generic `jobs` table has no columns for funding stage, company size,
    English-friendly, etc. `_score_opportunity` already treats a missing
    `company_payload` gracefully: it scores neutrally when no stage/size
    filter is set, and hard-excludes the row the moment a user sets an
    explicit `company_stage` filter (since `"x" not in ""` is always True) —
    see the plan notes for why this needed no changes to that function.
    """
    raw_text = f"{row.title} {row.company} {row.description or ''}".strip()
    # theirstack's live source_type is "theirstack_search" (see
    # providers/theirstack.py), everything else's live source_type matches
    # row.source directly (e.g. "greenhouse") - mirrored here so a cache hit
    # buckets/badges identically to a fresh live result (via
    # _result_source_bucket in engine.py).
    source_type = "theirstack_search" if row.source == "theirstack" else row.source
    source_label = "TheirStack" if row.source == "theirstack" else row.source.title()
    return {
        # Surfaced through _score_opportunity's return dict unchanged, so the
        # frontend can badge this distinctly from a fresh live fetch.
        "cache_hit": True,
        "opportunity_kind": "job",
        "company_name": row.company,
        "company_domain": None,
        "company_website_url": None,
        "company_careers_url": None,
        "role_title": row.title,
        "location": row.location,
        "country": row.country,
        "source_name": source_label,
        "source_type": source_type,
        "direct_apply_url": row.apply_url,
        "canonical_job_url": row.canonical_url,
        "portal_job_url": row.apply_url,
        "posted_at": row.posted_at,
        "company_payload": {},
        "contacts": [],
        "raw_text": raw_text,
        "description_text": row.description or None,
        "citation": {
            "source_name": source_label,
            "canonical_url": row.canonical_url,
            "job_url": row.apply_url,
            "posted_at": row.posted_at.isoformat() if row.posted_at else None,
            "evidence": ["Matched cached listing"],
            "extraction_note": "Served from the shared job cache.",
        },
    }


# Every source_type whose live results get written back into the shared
# `jobs` cache. Only these currently have a DB-first read path that could
# reuse them (theirstack, via _fetch_theirstack_db_candidates) or are worth
# banking for a future one (the ATS providers) - startupmap/web/indeed/apify
# stay live-only, unchanged, out of scope for this pass.
_CACHEABLE_SOURCE_TYPES = {"theirstack_search", "greenhouse", "lever", "ashby"}


def _opportunity_to_job_cache_row(item: dict[str, Any]) -> dict[str, Any] | None:
    """Adapt a freshly-fetched startup_hunt opportunity dict (theirstack or
    any ATS provider - see _CACHEABLE_SOURCE_TYPES) into job_search's flat
    upsert shape, so the existing `_upsert_jobs_cache` can write it into the
    shared `jobs` table unchanged. None of these carry a provider-native ID
    we can rely on being stable long-term, so the canonical URL doubles as
    the dedup key — same role canonical URLs already play everywhere else
    in this codebase."""
    canonical_url = item.get("canonical_job_url")
    apply_url = item.get("direct_apply_url") or item.get("portal_job_url") or canonical_url
    if not canonical_url or not apply_url:
        return None
    posted_at = item.get("posted_at")
    country_code = adzuna_country_code(item.get("country")) or None
    source_type = item.get("source_type") or ""
    provider_type = "theirstack" if source_type == "theirstack_search" else source_type
    return {
        "provider_type": provider_type,
        "external_job_id": canonical_url,
        "role": item.get("role_title") or "",
        "company": item.get("company_name") or "",
        "location": item.get("location") or "",
        "job_url": apply_url,
        "job_url_canonical": canonical_url,
        "posted_at": posted_at.isoformat() if isinstance(posted_at, datetime) else posted_at,
        "description_text": (item.get("description_text") or item.get("raw_text") or "")[:2000],
        "metadata": {"country": country_code, "salary_min": None, "salary_max": None, "category": None},
    }


async def _fetch_ats_db_candidates(
    db: AsyncSession,
    sources: list[StartupHuntSourceConfig],
    payload: dict[str, Any],
    strategy: dict[str, Any],
    existing: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[StartupHuntSourceConfig], list[uuid.UUID]]:
    """DB-first cache-first check for the ATS bucket (greenhouse/lever/
    ashby) - per-source, not query-driven like _fetch_theirstack_db_candidates
    below. Each ATS source here is one company's board, not a broad search,
    so "do we still need to fetch this live" is a per-company freshness
    question: if this company's board was fetched within
    startup_hunt_ats_cache_freshness_hours, reuse those cached rows and skip
    it; otherwise it goes into the still-needs-a-live-fetch list unchanged.

    Returns (scored cache-hit opportunities, sources that still need a live
    fetch, row ids to refresh TTL for). Non-ATS sources pass through
    untouched in the second element - callers can pass this function's
    output straight back into search_startup_hunt() as the new source list.
    """
    ats_types = {"greenhouse", "lever", "ashby"}
    ats_sources = [s for s in sources if s.type in ats_types]
    if not ats_sources:
        return [], sources, []

    live_sources = [s for s in sources if s.type not in ats_types]
    freshness_cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.startup_hunt_ats_cache_freshness_hours)

    scored: list[dict[str, Any]] = []
    row_ids: list[uuid.UUID] = []
    for source in ats_sources:
        rows = (
            await db.execute(
                select(Job).where(
                    Job.origin_tool == "startup_hunt",
                    Job.source == source.type,
                    Job.company == source.company,
                    Job.expires_at > datetime.now(timezone.utc),
                    Job.last_seen_at > freshness_cutoff,
                )
            )
        ).scalars().all()

        if not rows:
            live_sources.append(source)
            continue

        for row in rows:
            item = _job_row_to_opportunity_dict(row)
            scored_item, _ = _score_opportunity(item, payload, strategy, existing)
            if scored_item is not None:
                scored.append(scored_item)
            row_ids.append(row.id)

    return scored, live_sources, row_ids


async def _fetch_startup_hunt_db_candidates(
    db: AsyncSession, payload: dict[str, Any], strategy: dict[str, Any], existing: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[uuid.UUID]]:
    """DB-first pre-check driving the TheirStack shortfall decision (see
    plan) - deliberately NOT restricted to allowed_sources={"theirstack"}
    anymore. It used to be, on the reasoning that cached Greenhouse/Lever/
    Ashby rows "cover a different, unrelated set of companies" - true when
    every such row came from a user's own "My Sources" (already counted by
    _fetch_ats_db_candidates below), but false now that the background
    crawler (ingestion/job_sync.py) writes its own Greenhouse/Lever/Ashby/
    generic rows for companies nobody added as a source at all. Restricting
    to theirstack-only meant those crawler-synced rows - the whole point of
    running a crawler - never counted toward "do we still need to pay for a
    live TheirStack call," and were never otherwise reachable from search
    either (engine.py has no company_registry-aware bucket of its own).
    Dropping the restriction fixes both: crawler rows now surface here, and
    a company with enough crawler-sourced matches already can skip paying
    for TheirStack entirely.

    This does overlap with _fetch_ats_db_candidates for the narrow case of a
    "My Sources" company that also has a fresh per-source cache hit there -
    the same row gets scored in both places, inflating this function's
    return count and thus under-counting theirstack_db_shortfall slightly.
    Harmless: final results still go through _dedupe_opportunities before
    display, and skewing the shortfall calculation toward "we already have
    enough, skip the paid call" is the direction that matches this bucket's
    whole purpose.

    allowed_origin_tools={"startup_hunt"} is unrelated to the above and
    unchanged - it's what keeps recent_job_search's own cached rows
    (Adzuna/Bundesagentur/Arbeitnow - general market listings with no
    startup signal) from ever leaking into a startup-focused search.

    Returns already-scored opportunity dicts plus the underlying row ids
    (for TTL refresh), or ([], []) if the country can't be resolved, in
    which case the live theirstack fetch's own ProviderError-equivalent
    handling (settings.theirstack_api_key check) takes over exactly as
    before.
    """
    country_code = adzuna_country_code(payload.get("country")) or adzuna_country_code(payload.get("location"))
    if not country_code:
        return [], []

    theirstack_limit = int(payload.get("theirstack_limit") or settings.startup_hunt_theirstack_result_limit)
    rows = await query_job_cache_candidates(
        db,
        country_code=country_code,
        query_tokens=tokenize(str(payload.get("query") or "")),
        posted_within_hours=payload.get("posted_within_hours"),
        limit=max(300, theirstack_limit * 20),
        allowed_origin_tools={"startup_hunt"},
    )

    scored: list[dict[str, Any]] = []
    for row in rows:
        item = _job_row_to_opportunity_dict(row)
        scored_item, _ = _score_opportunity(item, payload, strategy, existing)
        if scored_item is not None:
            scored.append(scored_item)

    return scored, [row.id for row in rows]


def _normalize_scores_to_top_result(*item_lists: list[dict[str, Any]]) -> None:
    """Rescale score_total to 0-100 relative to the best result in this
    search, in place across all given lists together.

    The raw score from _score_opportunity is an open-ended sum of weighted
    signal bonuses (keyword matches, freshness, direct-apply link, seniority
    fit, etc.) with no fixed ceiling - a bare number like "29.268" has no
    reference point for a user to judge it against. Scaling every result
    against this search's own top score turns it into "how good is this
    compared to the best match here," which does.
    """
    all_items = [item for items in item_lists for item in items]
    if not all_items:
        return
    max_score = max(float(item.get("score_total") or 0) for item in all_items)
    if max_score <= 0:
        for item in all_items:
            item["score_total"] = 0.0
        return
    for item in all_items:
        raw = float(item.get("score_total") or 0)
        item["score_total"] = round(max(0.0, min(100.0, raw / max_score * 100)), 1)


def _response_cache_key(payload: dict[str, Any]) -> str:
    """Hashes the whole request payload (sorted keys), not a hand-picked
    subset like job_search's _response_cache_key - startup_hunt's payload
    affects result content in more places (e.g. strategy_prompt changes
    what TheirStack's live query looks like, not just post-fetch scoring
    the way job_search's preferences_prompt does), so picking a "safe to
    exclude" subset is genuinely harder to get right here. Hashing
    everything trades away a bit of cache-hit reuse (two searches differing
    only in, say, remote_only won't share a cache entry) for correctness
    that doesn't depend on remembering to update this list every time a new
    payload field is added."""
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return f"startup_hunt:{digest}"


def _strip_personalized_fields(response: dict[str, Any]) -> dict[str, Any]:
    """Shallow-copies the response and blanks out per-user save-state
    (saved/saved_status/saved_opportunity_id) before it goes into the
    shared Redis response cache. That cache has no user_id in its key
    (matching job_search's L1 cache design - shared across every user's
    searches), so caching one user's save-state as-is would leak it to
    every other user who later hits the same cache key. Re-attached fresh
    per request by _reattach_saved_state below."""
    def _strip_list(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        stripped = []
        for item in items:
            copy = dict(item)
            copy["saved"] = False
            copy["saved_status"] = None
            copy["saved_opportunity_id"] = None
            stripped.append(copy)
        return stripped

    return {
        **response,
        "results": _strip_list(response["results"]),
        "overflow_results": _strip_list(response["overflow_results"]),
    }


def _reattach_saved_state(response: dict[str, Any], existing: dict[str, dict[str, Any]]) -> None:
    """Inverse of _strip_personalized_fields, applied in place to a
    cache-hit response - re-attaches the CURRENT request's own
    saved-opportunity map. Every other field in the response is otherwise
    identical to what a fresh live search would have produced, since the
    cache key covers everything else that affects scoring/filtering/
    content."""
    for bucket_key in ("results", "overflow_results"):
        for item in response.get(bucket_key, []):
            match = existing.get(_opportunity_lookup_key(item))
            item["saved"] = bool(match)
            item["saved_status"] = match.get("opportunity_status") if match else None
            item["saved_opportunity_id"] = match.get("id") if match else None


_SINGLE_FLIGHT_LOCK_TTL_SECONDS = 20
_SINGLE_FLIGHT_POLL_INTERVAL_SECONDS = 0.5
_SINGLE_FLIGHT_MAX_WAIT_SECONDS = 10


async def search_startup_hunt_opportunities(db: AsyncSession, user_id: str, body) -> dict:
    existing = await _load_opportunity_map(db, user_id)
    payload = body.model_dump()

    cache_key = _response_cache_key(payload)
    try:
        cached = await get_cached(cache_key)
    except Exception:
        cached = None
    if cached:
        try:
            response = json.loads(cached)
            _reattach_saved_state(response, existing)
            return response
        except json.JSONDecodeError:
            pass

    # Single-flight: if many requests hit this exact uncached search at
    # once, only the lock-holder does the real DB+provider work - everyone
    # else waits briefly for its result to land in the response cache and
    # reuses it, instead of each independently fanning out to every
    # provider. Fails open (treats as leader) on a Redis error, and a
    # follower that times out waiting falls through to doing its own fetch
    # rather than hanging forever on a slow or stuck leader. Same pattern
    # job_search's search_recent_jobs uses.
    try:
        is_leader = await acquire_lock(f"{cache_key}:lock", _SINGLE_FLIGHT_LOCK_TTL_SECONDS)
    except Exception:
        is_leader = True

    if not is_leader:
        waited = 0.0
        while waited < _SINGLE_FLIGHT_MAX_WAIT_SECONDS:
            await asyncio.sleep(_SINGLE_FLIGHT_POLL_INTERVAL_SECONDS)
            waited += _SINGLE_FLIGHT_POLL_INTERVAL_SECONDS
            try:
                cached = await get_cached(cache_key)
            except Exception:
                cached = None
            if cached:
                try:
                    response = json.loads(cached)
                    _reattach_saved_state(response, existing)
                    return response
                except json.JSONDecodeError:
                    break

    # Both the global curated list AND a user's own added sources are gated
    # behind include_seeded_sources - turning that toggle off means NEITHER
    # gets searched, full stop (see engine.py's search_startup_hunt, which
    # is the actual enforcement point for the live-fetch path below).
    # list_user_startup_hunt_sources returns every status (the
    # source-management UI needs pending/failed rows too) - only 'resolved'
    # ones are actually searchable.
    global_sources = build_seeded_sources(await list_global_startup_hunt_sources(db))
    resolved_user_sources = [s for s in await list_user_startup_hunt_sources(db, user_id) if s.get("status") == "resolved"]
    user_sources = build_seeded_sources(resolved_user_sources)

    strategy = await parse_strategy_prompt(payload.get("strategy_prompt"))

    db_scored: list[dict[str, Any]] = []
    db_job_ids: list[uuid.UUID] = []

    # ATS (greenhouse/lever/ashby) DB-first cache-first check - per-source
    # freshness, not the query-driven shortfall theirstack uses below (see
    # _fetch_ats_db_candidates). Whichever sources have a fresh-enough cache
    # hit get pulled out of global_sources/user_sources here, so they don't
    # ALSO get live-fetched a few lines down inside search_startup_hunt().
    #
    # Gated on include_seeded_sources too, same as the live path - without
    # this, a source with a cache hit from an earlier search (toggle on)
    # would keep surfacing here on every later search even with the toggle
    # off, since this check runs against global_sources/user_sources
    # directly and never goes through search_startup_hunt()'s own gate.
    if payload.get("include_seeded_sources") and (
        settings.startup_hunt_greenhouse_enabled or settings.startup_hunt_lever_enabled or settings.startup_hunt_ashby_enabled
    ):
        global_ats_scored, global_sources, global_ats_row_ids = await _fetch_ats_db_candidates(
            db, global_sources, payload, strategy, existing
        )
        user_ats_scored, user_sources, user_ats_row_ids = await _fetch_ats_db_candidates(
            db, user_sources, payload, strategy, existing
        )
        db_scored.extend(global_ats_scored + user_ats_scored)
        db_job_ids.extend(global_ats_row_ids + user_ats_row_ids)

    # DB-first shortfall check driving the theirstack live-call decision (see
    # plan). Draws on every startup_hunt-origin DB row now, not just
    # theirstack's own cache - see _fetch_startup_hunt_db_candidates'
    # docstring for why. The other 6 buckets run exactly as they always
    # have, fully live, every search. theirstack_enabled/theirstack_limit
    # are no longer real request fields (removed along with the old
    # per-request provider toggles) - this is purely an internal signal for
    # engine.py's _bucket_enabled()/theirstack.py's fetch(), which both
    # check payload FIRST before falling back to the
    # startup_hunt_theirstack_enabled/_result_limit config defaults.
    theirstack_db_shortfall = 0
    theirstack_live_limit = 0
    if settings.startup_hunt_theirstack_enabled:
        theirstack_scored, theirstack_row_ids = await _fetch_startup_hunt_db_candidates(db, payload, strategy, existing)
        db_scored.extend(theirstack_scored)
        db_job_ids.extend(theirstack_row_ids)
        theirstack_limit = int(payload.get("theirstack_limit") or settings.startup_hunt_theirstack_result_limit)
        theirstack_db_shortfall = theirstack_limit - len(theirstack_scored)
        theirstack_live_limit = min(settings.theirstack_max_page_size, max(1, theirstack_db_shortfall) * 2)

    # Cost-aware fetch ordering, phase 1: every enabled bucket EXCEPT
    # TheirStack, the only metered/paid Startup Hunt source. Mirrors
    # job_search's free-providers-before-metered pattern - instead of firing
    # TheirStack in parallel with the free ATS/web buckets regardless of
    # whether they'd have covered the request alone, fetch the free buckets
    # first and only pay for a live TheirStack call (phase 2 below) for
    # whatever shortfall remains after seeing their actual live yield, not
    # just the DB-cache shortfall computed above.
    phase1_payload = dict(payload)
    phase1_payload["theirstack_enabled"] = False
    (
        results, overflow_results, filtered_out, parsed_strategy,
        configured_source_count, source_result_counts, source_diagnostics, raw_fetched,
    ) = await search_startup_hunt(phase1_payload, existing, global_sources, user_sources, strategy=strategy)

    if theirstack_db_shortfall > 0:
        result_limit = int(payload.get("result_limit") or 25)
        covered_so_far = len(_dedupe_opportunities(db_scored + results + overflow_results))
        if covered_so_far < result_limit:
            # Phase 2: TheirStack only - global_sources/user_sources passed
            # empty (those are what feed the ATS bucket; already fetched in
            # phase 1, no reason to fetch them again) and web_enabled forced
            # off (google_web is off by default, but if it's ever turned on,
            # phase 1 already covered it too).
            phase2_payload = dict(payload)
            phase2_payload["theirstack_enabled"] = True
            phase2_payload["theirstack_limit"] = theirstack_live_limit
            phase2_payload["web_enabled"] = False
            (
                ts_results, ts_overflow, ts_filtered_out, _phase2_strategy,
                ts_configured_count, ts_source_result_counts, ts_source_diagnostics, ts_raw_fetched,
            ) = await search_startup_hunt(phase2_payload, existing, [], [], strategy=strategy)
            results = results + ts_results
            overflow_results = overflow_results + ts_overflow
            filtered_out = filtered_out + ts_filtered_out
            configured_source_count += ts_configured_count
            source_result_counts["theirstack"] = ts_source_result_counts.get("theirstack", 0)
            if ts_source_diagnostics.get("theirstack"):
                source_diagnostics["theirstack"] = ts_source_diagnostics["theirstack"]
            raw_fetched = raw_fetched + ts_raw_fetched

    # Upsert every raw theirstack + ATS (greenhouse/lever/ashby) item this
    # search actually fetched live into the shared cache, so a repeat search
    # covering the same companies/roles can be served from the DB instead of
    # hitting those providers live again - same pattern job_search's
    # search_recent_jobs uses (cache the full raw fetch, filter at read
    # time). Uses raw_fetched, not results/overflow_results - those are the
    # post-filter survivors only, so caching just them would mean an item
    # hard-excluded by THIS search's own filters (wrong seniority, no
    # keyword match, etc.) - which may well match a later, differently-
    # filtered search - gets thrown away and re-fetched live next time
    # instead of being reused. Runs before the db_scored merge below, so
    # this only ever sees fresh live results, never re-upserts a cache hit.
    fresh_cacheable_rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in raw_fetched:
        if item.get("source_type") not in _CACHEABLE_SOURCE_TYPES:
            continue
        row = _opportunity_to_job_cache_row(item)
        if row is None:
            continue
        # raw_fetched isn't deduped (unlike results/overflow_results, which
        # went through _dedupe_opportunities) - the same job can legitimately
        # appear twice here (e.g. a company that's both globally curated and
        # in a user's own sources). A single upsert statement with the same
        # (source, source_job_id) key twice would error, so dedupe on that
        # key here rather than relying on the upsert to handle it.
        fresh_cacheable_rows_by_key[(row["provider_type"], row["external_job_id"])] = row
    fresh_cacheable_rows = list(fresh_cacheable_rows_by_key.values())
    if fresh_cacheable_rows:
        await _upsert_jobs_cache(db, fresh_cacheable_rows, origin_tool="startup_hunt")
    if db_job_ids:
        await touch_job_cache_rows(db, db_job_ids, ttl_days=settings.job_search_cache_ttl_days)

    if db_scored:
        result_limit = int(payload.get("result_limit") or 25)
        combined = _dedupe_opportunities(db_scored + results)
        combined.sort(key=lambda item: -float(item.get("score_total") or 0))
        results = combined[:result_limit]
        overflow_results = combined[result_limit:] + overflow_results

    _normalize_scores_to_top_result(results, overflow_results)

    response = {
        "results": results,
        "overflow_results": overflow_results,
        "filtered_out": filtered_out,
        "parsed_strategy": parsed_strategy,
        "configured_source_count": configured_source_count,
        "source_result_counts": source_result_counts,
        "source_diagnostics": source_diagnostics,
    }

    try:
        await set_cached(
            cache_key,
            json.dumps(_strip_personalized_fields(response)),
            jittered_ttl(settings.startup_hunt_response_cache_ttl_seconds),
        )
    except Exception:
        pass

    return response


async def list_startup_hunt_opportunities(db: AsyncSession, user_id: str) -> list[dict]:
    rows = await OpportunityRepository(db).list(user_id, order_by=StartupHuntOpportunity.created_at.desc())
    return [row_to_dict(r) for r in rows]


async def get_startup_hunt_opportunity(db: AsyncSession, user_id: str, opportunity_id: str) -> dict:
    row = await OpportunityRepository(db).get(user_id, opportunity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="startup_hunt_opportunities row not found")
    return row_to_dict(row)


async def list_startup_hunt_contacts(db: AsyncSession, user_id: str, opportunity_id: str | None) -> list[dict]:
    stmt = select(StartupHuntContact).where(StartupHuntContact.user_id == user_id)
    if opportunity_id:
        stmt = stmt.where(StartupHuntContact.opportunity_id == opportunity_id)
    stmt = stmt.order_by(StartupHuntContact.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [row_to_dict(r) for r in rows]


async def get_artifact_counts(db: AsyncSession, user_id: str) -> dict[str, int]:
    rows = (
        await db.execute(
            select(OpportunityArtifact.opportunity_id, func.count())
            .where(OpportunityArtifact.user_id == user_id, OpportunityArtifact.opportunity_id.is_not(None))
            .group_by(OpportunityArtifact.opportunity_id)
        )
    ).all()
    return {str(oid): count for oid, count in rows}


async def list_opportunity_artifacts(db: AsyncSession, user_id: str, opportunity_id: str) -> list[dict]:
    rows = (
        await db.execute(
            select(OpportunityArtifact)
            .where(OpportunityArtifact.user_id == user_id, OpportunityArtifact.opportunity_id == opportunity_id)
            .order_by(OpportunityArtifact.created_at.desc())
        )
    ).scalars().all()
    return [row_to_dict(r) for r in rows]


async def create_opportunity_artifact(db: AsyncSession, user_id: str, opportunity_id: str, body: dict) -> dict:
    artifact_type = body.get("artifact_type", "")
    if artifact_type not in {"resume_analysis", "cover_letter", "interview_prep"}:
        raise HTTPException(status_code=422, detail="Invalid artifact_type")
    obj = OpportunityArtifact(
        user_id=user_id,
        opportunity_id=opportunity_id,
        artifact_type=artifact_type,
        tool_used=body.get("tool_used", artifact_type),
        content=body.get("content", ""),
        metadata_=body.get("metadata", {}),
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return row_to_dict(obj)


async def delete_opportunity_artifact(db: AsyncSession, user_id: str, opportunity_id: str, artifact_id: str) -> None:
    row = (
        await db.execute(
            select(OpportunityArtifact).where(
                OpportunityArtifact.id == artifact_id,
                OpportunityArtifact.opportunity_id == opportunity_id,
                OpportunityArtifact.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await db.delete(row)
    await db.flush()


async def _find_registry_company_id(db: AsyncSession, domain: str | None) -> str | None:
    """Best-effort link from a user's saved StartupHuntCompany back to the
    global crawler registry (see models.py::CompanyRegistry), by domain only
    - the one dedup key both tables actually agree on. None (no match, or no
    domain to match on) is a normal, expected outcome, not an error: most
    saved companies today come from live search sources the crawler hasn't
    (yet) discovered independently."""
    if not domain:
        return None
    row_id = (
        await db.execute(select(CompanyRegistry.id).where(CompanyRegistry.domain == domain))
    ).scalar_one_or_none()
    return str(row_id) if row_id is not None else None


async def _upsert_company(db: AsyncSession, user_id: str, payload: dict) -> str:
    company_payload = payload.get("company_payload") or {}
    existing = (
        await db.execute(
            select(StartupHuntCompany).where(
                StartupHuntCompany.user_id == user_id, StartupHuntCompany.company_name == payload["company_name"]
            )
        )
    ).scalar_one_or_none()

    registry_company_id = await _find_registry_company_id(db, payload.get("company_domain"))

    fields = dict(
        company_name=payload["company_name"],
        company_domain=payload.get("company_domain"),
        company_website_url=payload.get("company_website_url"),
        company_careers_url=payload.get("company_careers_url"),
        country=payload.get("country"),
        city=company_payload.get("city"),
        stage=company_payload.get("stage"),
        company_size=company_payload.get("company_size"),
        ai_relevance=company_payload.get("ai_relevance"),
        english_friendly=bool(company_payload.get("english_friendly")),
        relocation_support=company_payload.get("relocation_support"),
        source_payload=company_payload,
        registry_company_id=registry_company_id,
    )

    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        await db.flush()
        return str(existing.id)

    new_row = StartupHuntCompany(user_id=user_id, **fields)
    db.add(new_row)
    await db.flush()
    return str(new_row.id)


async def _replace_contacts(
    db: AsyncSession, user_id: str, opportunity_id: str, contacts: list[dict], company_id: str | None
) -> None:
    await db.execute(
        StartupHuntContact.__table__.delete().where(
            StartupHuntContact.user_id == user_id, StartupHuntContact.opportunity_id == opportunity_id
        )
    )
    if not contacts:
        await db.flush()
        return
    for contact in contacts:
        db.add(
            StartupHuntContact(
                user_id=user_id,
                opportunity_id=opportunity_id,
                company_id=company_id,
                name=contact.get("name"),
                title=contact.get("title"),
                contact_type=contact.get("contact_type"),
                email=contact.get("email"),
                email_confidence=contact.get("email_confidence"),
                linkedin_url=contact.get("linkedin_url"),
                source=contact.get("source"),
                provider_chain=contact.get("provider_chain") or [],
            )
        )
    await db.flush()


async def _find_job_id(db: AsyncSession, *, source_type: str, canonical_job_url: str | None) -> str | None:
    """Trace a saved opportunity back to its shared `jobs` cache row, when
    available. Only theirstack-sourced saves can have one today — the other
    6 buckets don't write into the shared cache yet (see plan)."""
    if source_type != "theirstack_search" or not canonical_job_url:
        return None
    row = (
        await db.execute(
            select(Job.id).where(Job.source == "theirstack", Job.canonical_url == canonical_job_url)
        )
    ).scalar_one_or_none()
    return str(row) if row is not None else None


def _url_fields(payload: dict) -> dict:
    direct_apply_url = str(payload["direct_apply_url"]) if payload.get("direct_apply_url") else None
    canonical_job_url = (
        str(payload["canonical_job_url"])
        if payload.get("canonical_job_url")
        else (canonicalize_url(direct_apply_url) if direct_apply_url else None)
    )
    portal_job_url = str(payload["portal_job_url"]) if payload.get("portal_job_url") else None
    company_website_url = str(payload["company_website_url"]) if payload.get("company_website_url") else None
    company_careers_url = str(payload["company_careers_url"]) if payload.get("company_careers_url") else None
    return {
        "direct_apply_url": direct_apply_url,
        "canonical_job_url": canonical_job_url,
        "portal_job_url": portal_job_url,
        "company_website_url": company_website_url,
        "company_careers_url": company_careers_url,
    }


async def create_startup_hunt_opportunity(
    db: AsyncSession, user_id: str, body: StartupHuntOpportunityCreateRequest
) -> dict:
    payload = body.model_dump()
    payload.update(_url_fields(payload))
    payload["company_domain"] = payload.get("company_domain") or extract_domain(
        payload["company_website_url"] or payload["company_careers_url"] or payload["direct_apply_url"]
    )
    payload["discovered_at"] = payload.get("discovered_at") or datetime.now(timezone.utc).isoformat()

    existing = (
        await db.execute(
            select(StartupHuntOpportunity).where(
                StartupHuntOpportunity.user_id == user_id,
                StartupHuntOpportunity.company_name == payload["company_name"],
                StartupHuntOpportunity.role_title == payload["role_title"],
                StartupHuntOpportunity.location == payload["location"],
            )
        )
    ).scalar_one_or_none()

    # Preserves whatever tracker_application_id an already-migrated row happened
    # to carry, but never sets one on new writes - startup_hunt_opportunities is
    # its own tracked list now (the Tracker's "Startup Leads" tab), not synced
    # into the Tracker's manual job_applications table.
    tracker_id = str(existing.tracker_application_id) if (existing and existing.tracker_application_id) else None

    company_id = await _upsert_company(db, user_id, payload)
    job_id = await _find_job_id(
        db, source_type=payload["source_type"], canonical_job_url=payload.get("canonical_job_url")
    )

    fields = dict(
        company_name=payload["company_name"],
        company_domain=payload["company_domain"],
        company_website_url=payload["company_website_url"],
        company_careers_url=payload["company_careers_url"],
        role_title=payload["role_title"],
        location=payload["location"],
        country=payload.get("country"),
        source_name=payload["source_name"],
        source_type=payload["source_type"],
        direct_apply_url=payload["direct_apply_url"],
        canonical_job_url=payload["canonical_job_url"],
        portal_job_url=payload["portal_job_url"],
        posted_at=_parse_dt(payload.get("posted_at")),
        discovered_at=_parse_dt(payload["discovered_at"]),
        opportunity_kind=payload["opportunity_kind"],
        opportunity_status=payload["opportunity_status"],
        score_total=Decimal(str(payload.get("score_total") or 0)),
        score_labels=payload.get("score_labels") or [],
        score_reasons=payload.get("score_reasons") or [],
        citation_payload=payload["citation_payload"],
        company_payload=payload.get("company_payload") or {},
        search_context=payload.get("search_context") or {},
        user_id=user_id,
        tracker_application_id=tracker_id,
        company_id=company_id,
        job_id=job_id,
    )

    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        await db.flush()
        await db.refresh(existing)
        await _replace_contacts(db, user_id, str(existing.id), payload.get("contacts", []), company_id)
        return row_to_dict(existing)

    new_row = StartupHuntOpportunity(**fields)
    db.add(new_row)
    await db.flush()
    await db.refresh(new_row)
    await _replace_contacts(db, user_id, str(new_row.id), payload.get("contacts", []), company_id)
    return row_to_dict(new_row)


async def update_startup_hunt_opportunity(
    db: AsyncSession, user_id: str, opportunity_id: str, body: StartupHuntOpportunityUpdateRequest
) -> dict:
    existing = (
        await db.execute(
            select(StartupHuntOpportunity).where(
                StartupHuntOpportunity.id == opportunity_id, StartupHuntOpportunity.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="Not found")

    direct_apply_url = str(body.direct_apply_url) if body.direct_apply_url else existing.direct_apply_url
    canonical_job_url = str(body.canonical_job_url) if body.canonical_job_url else existing.canonical_job_url

    existing.opportunity_status = body.opportunity_status
    existing.direct_apply_url = direct_apply_url
    existing.canonical_job_url = canonical_job_url

    await db.flush()
    await db.refresh(existing)
    return row_to_dict(existing)


async def delete_startup_hunt_opportunity(db: AsyncSession, user_id: str, opportunity_id: str) -> None:
    ok = await OpportunityRepository(db).delete(user_id, opportunity_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")


# ── Startup Hunt Sources (global curated + per-user custom) ──────────────

class StartupHuntSourceRepository(UserScopedRepository[StartupHuntSource]):
    model = StartupHuntSource


async def list_global_startup_hunt_sources(db: AsyncSession) -> list[dict]:
    """The curated source list visible to every user (user_id IS NULL) — still
    gated behind include_seeded_sources + the "crawler" bucket toggle.
    status='resolved' only - a 'pending'/'failed' row has no usable
    type/slug yet (build_seeded_sources would silently drop it anyway
    since type=None never matches ALLOWED_SOURCE_TYPES, but filtering here
    is the actual documented intent, not an incidental side effect)."""
    stmt = select(StartupHuntSource).where(
        StartupHuntSource.user_id.is_(None), StartupHuntSource.status == "resolved"
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [row_to_dict(r) for r in rows]


async def list_user_startup_hunt_sources(db: AsyncSession, user_id: str) -> list[dict]:
    """This user's own sources, every status - the source-management UI
    needs to show pending/failed rows too (status badge, poll-until-done),
    not just resolved ones. search_startup_hunt_opportunities filters this
    down to 'resolved' itself before feeding it into the search pipeline."""
    rows = await StartupHuntSourceRepository(db).list(user_id, order_by=StartupHuntSource.created_at.desc())
    return [row_to_dict(r) for r in rows]


async def create_startup_hunt_source(db: AsyncSession, user_id: str, body: StartupHuntSourceIn) -> dict:
    """Manual entry - the fallback path when the 'smart add' resolve flow
    (see resolve_startup_hunt_source below) can't find a company on its own.
    Whatever the caller passes here is trusted as already-resolved."""
    obj = await StartupHuntSourceRepository(db).create(
        user_id,
        type=body.type,
        name=body.name,
        company=body.company or body.name,
        slug=body.slug,
        url=str(body.url) if body.url else None,
        metadata_=body.metadata,
    )
    return row_to_dict(obj)


async def resolve_startup_hunt_source(
    db: AsyncSession, user_id: str, company_input: str, arq_pool: ArqRedis
) -> dict:
    """Entry point for My Sources' "smart add" flow - the user types a
    company name or pastes a careers URL, this figures out the rest (see
    resolver.py). Three tiers, fastest first:

    1. Reuse: some user (any user - a resolved ATS type/slug is a fact
       about the company, not about who added it) already resolved a
       matching name. Instant, no external calls.
    2. Fast sync resolve: one direct slug guess (or a pasted URL's own
       pattern/page scan) against Greenhouse/Lever/Ashby, bounded to
       ~startup_hunt_resolve_sync_timeout_seconds. Typically 1-2s.
    3. Async fallback: doesn't land in step 2 -> create a 'pending' row
       immediately and hand it to a background ARQ job (tasks.py) that
       tries harder. The frontend polls the sources list until it flips to
       'resolved' or 'failed'.
    """
    company_input = company_input.strip()
    if not company_input:
        raise HTTPException(status_code=400, detail="Enter a company name or careers URL.")

    normalized = company_input.lower()
    reusable = (
        await db.execute(
            select(StartupHuntSource)
            .where(StartupHuntSource.status == "resolved", func.lower(StartupHuntSource.name) == normalized)
            .limit(1)
        )
    ).scalars().first()

    if reusable is not None:
        obj = await StartupHuntSourceRepository(db).create(
            user_id,
            type=reusable.type,
            name=company_input,
            company=reusable.company,
            slug=reusable.slug,
            url=reusable.url,
            metadata_={},
            status="resolved",
        )
        return row_to_dict(obj)

    try:
        resolved = await asyncio.wait_for(
            resolver.try_direct_resolve(company_input),
            timeout=settings.startup_hunt_resolve_sync_timeout_seconds,
        )
    except (asyncio.TimeoutError, TimeoutError):
        resolved = None

    if resolved is not None:
        obj = await StartupHuntSourceRepository(db).create(
            user_id,
            type=resolved.type,
            name=company_input,
            company=company_input,
            slug=resolved.slug,
            url=resolved.url,
            metadata_={},
            status="resolved",
        )
        return row_to_dict(obj)

    pending = await StartupHuntSourceRepository(db).create(
        user_id,
        type=None,
        name=company_input,
        company=company_input,
        slug=None,
        url=company_input if company_input.lower().startswith(("http://", "https://")) else None,
        metadata_={},
        status="pending",
    )
    await arq_pool.enqueue_job("resolve_startup_hunt_source_task", source_id=str(pending.id))
    return row_to_dict(pending)


async def delete_startup_hunt_source(db: AsyncSession, user_id: str, source_id: str) -> None:
    ok = await StartupHuntSourceRepository(db).delete(user_id, source_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
