"""Startup Hunt v2 provider layer for startup-first discovery and contact enrichment."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

from app.ai.llm import provider as ai_provider
from app.core.config import settings
from app.services.cache import cached_prompt_parse

logger = logging.getLogger(__name__)


@dataclass
class StartupHuntSourceConfig:
    type: str
    name: str
    company: str
    slug: str | None = None
    url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


SOURCE_BUCKETS = ("crawler", "startupmap", "web", "indeed", "theirstack", "apify", "ats")
APIFY_TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}
INFRASTRUCTURE_HOST_MARKERS = (
    "supabase.co",
    "supabase.in",
    "vercel.app",
    "netlify.app",
    "herokuapp.com",
    "render.com",
    "railway.app",
)
SHORTENER_OR_PROXY_HOSTS = (
    "bit.ly",
    "grnh.se",
    "lnkd.in",
    "t.co",
    "tinyurl.com",
)
ATS_HOST_MARKERS = (
    "ashbyhq.com",
    "greenhouse.io",
    "lever.co",
    "join.com",
    "workable.com",
    "smartrecruiters.com",
    "myworkdayjobs.com",
    "wd3.myworkdayjobs.com",
    "kenjo.io",
    "teamtailor.com",
    "personio.de",
    "jobs.personio.de",
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str | None) -> datetime | None:
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


def canonicalize_url(url: str) -> str:
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


COUNTRY_CODE_OVERRIDES = {
    "germany": "de",
    "deutschland": "de",
    "united states": "us",
    "usa": "us",
    "united kingdom": "uk",
    "uk": "uk",
    "great britain": "uk",
    "france": "fr",
    "spain": "es",
    "italy": "it",
    "netherlands": "nl",
    "belgium": "be",
    "austria": "at",
    "switzerland": "ch",
    "poland": "pl",
    "portugal": "pt",
    "ireland": "ie",
    "canada": "ca",
    "australia": "au",
}


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


_COUNTRY_NAME_TO_CODE = dict(COUNTRY_CODE_OVERRIDES)
_COUNTRY_CODE_TO_NAMES: dict[str, set[str]] = {}
for _name, _code in COUNTRY_CODE_OVERRIDES.items():
    _COUNTRY_CODE_TO_NAMES.setdefault(_code, set()).add(_name)


def _country_aliases(value: str) -> set[str]:
    text = normalize_text(value)
    if not text:
        return set()
    aliases = {text}
    code = _COUNTRY_NAME_TO_CODE.get(text)
    if len(text) == 2:
        code = text
    if code:
        aliases.add(code)
        aliases.update(_COUNTRY_CODE_TO_NAMES.get(code, set()))
    return aliases


def _location_matches(
    location_target: str,
    country_target: str,
    location_text: str,
    company_payload: dict[str, Any],
    is_remote: bool,
) -> bool:
    if not location_target and not country_target:
        return True
    if location_target and location_target in location_text:
        return True
    target_country_aliases = _country_aliases(country_target) if country_target else set()
    if target_country_aliases:
        if any(alias and alias in location_text for alias in target_country_aliases):
            return True
        company_country_aliases = _country_aliases(str(company_payload.get("country", "") or ""))
        if target_country_aliases & company_country_aliases:
            return True
        # Remote/EU postings: accept when targeting an EU country and the role is remote or EU-tagged.
        eu_codes = {"de", "fr", "es", "it", "nl", "be", "at", "ch", "pl", "pt", "ie", "uk"}
        if target_country_aliases & eu_codes:
            if is_remote and any(token in location_text for token in ("europe", "eu", "emea", "remote")):
                return True
    if not country_target and is_remote:
        return True
    return False


def tokenize(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 1]


def _normalize_role_query_aliases(value: str) -> str:
    text = normalize_text(value)
    replacements = {
        " ai/ml ": " ai ml ",
        " common ai/ml engineer ": " ai ml engineer ",
        " common ai ml engineer ": " ai ml engineer ",
        " ai/ml engineer ": " ai ml engineer ",
        " ai eng ": " ai engineer ",
        " ml eng ": " ml engineer ",
        " llm eng ": " llm engineer ",
        " applied ai eng ": " applied ai engineer ",
        " ml ops ": " mlops ",
        " eng ": " engineer ",
        " sw eng ": " software engineer ",
        " jobs ": " job ",
    }
    padded = f" {text} "
    for source, target in replacements.items():
        padded = padded.replace(source, target)
    return normalize_text(padded)


def _ai_engineer_family_variants(query: str) -> list[str]:
    normalized = _normalize_role_query_aliases(query)
    variants: list[str] = []

    if (
        "ai engineer" in normalized
        or "applied ai engineer" in normalized
        or "ml engineer" in normalized
        or "machine learning engineer" in normalized
        or "llm engineer" in normalized
        or "nlp engineer" in normalized
        or "mlops engineer" in normalized
        or "ai platform engineer" in normalized
        or "ml research engineer" in normalized
        or "research engineer" in normalized
        or ("ai" in normalized and "engineer" in normalized)
    ):
        variants.extend(
            [
                "AI Engineer",
                "Applied AI Engineer",
                "ML Engineer",
                "Machine Learning Engineer",
                "LLM Engineer",
                "MLOps Engineer",
                "NLP Engineer",
                "AI Platform Engineer",
                "Research Engineer",
                "Applied Research Engineer",
                "ML Research Engineer",
            ]
        )

    if "data scientist" in normalized:
        variants.extend(["Data Scientist", "Applied Scientist", "Machine Learning Scientist"])

    compact_query = query.strip()
    if compact_query:
        variants.insert(0, compact_query)

    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        key = normalize_text(variant)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(variant)
    return deduped[:8] or [compact_query or "AI Engineer"]


def extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host or None


ALLOWED_SOURCE_TYPES = {
    "greenhouse", "lever", "ashby", "startup_company", "startup_directory",
    "google_web", "web_search", "ats_discovery", "apify_actor", "indeed_search", "theirstack_search",
}


def build_seeded_sources(rows: list[dict[str, Any]]) -> list[StartupHuntSourceConfig]:
    """Convert startup_hunt_sources DB rows (global + this user's own, already
    merged by the caller) into the config shape the search engine consumes.

    Replaces the old STARTUP_HUNT_SOURCES_JSON env parsing — same validation
    rules, just fed from the DB instead of a static env blob.
    """
    sources: list[StartupHuntSourceConfig] = []
    for item in rows:
        source_type = str(item.get("type", "")).strip().lower()
        name = str(item.get("name", "")).strip()
        company = str(item.get("company", "")).strip() or name
        slug = str(item.get("slug", "")).strip() or None
        url = str(item.get("url", "")).strip() or None
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if not name or source_type not in ALLOWED_SOURCE_TYPES:
            continue
        sources.append(
            StartupHuntSourceConfig(
                type=source_type,
                name=name,
                company=company,
                slug=slug,
                url=url,
                metadata=metadata,
            )
        )
    return sources


def _source_host(source: StartupHuntSourceConfig) -> str:
    if not source.url:
        return ""
    parsed = urlparse(source.url)
    return parsed.netloc.lower().strip()


async def parse_strategy_prompt(prompt: str | None) -> dict[str, Any]:
    if not prompt or not prompt.strip():
        return {
            "keywords": [],
            "languages": [],
            "company_stage": None,
            "preferred_cities": [],
            "hidden_gem_signals": [],
            "contact_focus": [],
            "seniority_preference": None,
        }

    async def _parse() -> dict[str, Any]:
        system = """Extract structured startup-hunt preferences from the user prompt.
Return JSON only:
{
  "keywords": [string],
  "languages": [string],
  "company_stage": string | null,
  "preferred_cities": [string],
  "hidden_gem_signals": [string],
  "contact_focus": [string],
  "seniority_preference": string | null
}
Normalize values into short lowercase phrases."""

        try:
            text = await ai_provider.generate_text(prompt.strip(), system=system, max_tokens=300, tier="light")
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return {
                    "keywords": [str(v).strip().lower() for v in data.get("keywords", []) if str(v).strip()],
                    "languages": [str(v).strip().lower() for v in data.get("languages", []) if str(v).strip()],
                    "company_stage": str(data.get("company_stage")).strip().lower() if data.get("company_stage") else None,
                    "preferred_cities": [str(v).strip().lower() for v in data.get("preferred_cities", []) if str(v).strip()],
                    "hidden_gem_signals": [str(v).strip().lower() for v in data.get("hidden_gem_signals", []) if str(v).strip()],
                    "contact_focus": [str(v).strip().lower() for v in data.get("contact_focus", []) if str(v).strip()],
                    "seniority_preference": _normalize_seniority_preference(str(data.get("seniority_preference"))) if data.get("seniority_preference") else None,
                }
        except Exception:
            pass

        lowered = prompt.lower()
        return {
            "keywords": tokenize(prompt),
            "languages": ["english"] if "english" in lowered else [],
            "company_stage": "pre-seed" if "pre seed" in lowered or "pre-seed" in lowered else ("seed" if "seed" in lowered else None),
            "preferred_cities": [city for city in ["berlin", "munich", "hamburg", "cologne", "germany"] if city in lowered],
            "hidden_gem_signals": [signal for signal in ["small startup", "early access", "founder-led", "hidden gems"] if signal.split()[0] in lowered],
            "contact_focus": [focus for focus in ["founder", "ceo", "hiring manager", "head of ai"] if focus in lowered],
            "seniority_preference": _infer_seniority_preference_from_prompt(prompt),
        }

    return await cached_prompt_parse(
        "startup_hunt_strategy", prompt.strip(), settings.prompt_parse_cache_ttl_seconds, _parse
    )


async def search_startup_hunt(
    payload: dict[str, Any],
    existing_opportunities: dict[str, dict[str, Any]],
    global_sources: list[StartupHuntSourceConfig] | None = None,
    user_sources: list[StartupHuntSourceConfig] | None = None,
    strategy: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], int, dict[str, int], dict[str, dict[str, Any]]]:
    sources: list[StartupHuntSourceConfig] = []
    # Previously also required _bucket_enabled(payload, "crawler") - a
    # per-request bucket toggle that had no UI control and always defaulted
    # False, so this condition was permanently unreachable: global (curated)
    # seeded sources - including any greenhouse/lever/ashby company boards -
    # never actually got included regardless of what a user set
    # include_seeded_sources to. include_seeded_sources is a real, distinct
    # request field with its own UI toggle (unlike the bucket bools, which
    # are gone now) - that alone is the intended gate here.
    if payload.get("include_seeded_sources"):
        sources.extend(global_sources or [])
    # A user's own explicitly-added sources are always searched — no reason to
    # hide them behind the (currently off-by-default) crawler bucket toggle.
    sources.extend(user_sources or [])
    sources.extend(_auto_sources_from_integrations(payload))
    sources.extend(_auto_dynamic_sources(payload))
    # Callers that already parsed strategy_prompt (e.g. to score DB-cache
    # candidates before deciding how much of a live fetch is still needed)
    # can pass it in directly to avoid a second LLM parse of the same prompt.
    if strategy is None:
        strategy = await parse_strategy_prompt(payload.get("strategy_prompt"))
    if not sources:
        return [], [], [], strategy, 0, {bucket: 0 for bucket in SOURCE_BUCKETS}, _build_source_diagnostics(payload, [], [])

    total_budget = float(getattr(settings, "startup_hunt_total_budget_seconds", 150))
    bucket_fatal: dict[str, str] = {}
    # Buckets that should be sequential so a credit/auth error short-circuits the rest.
    sequential_buckets = {"apify"}

    async def _per_bucket_sequential(bucket_sources: list[StartupHuntSourceConfig]) -> list[tuple[int, dict[str, Any]]]:
        out: list[tuple[int, dict[str, Any]]] = []
        for src in bucket_sources:
            idx = sources.index(src)
            result = await _fetch_source_safe(client, src, payload, strategy, bucket_fatal=bucket_fatal)
            out.append((idx, result))
        return out

    async with httpx.AsyncClient(timeout=settings.startup_hunt_timeout_seconds, follow_redirects=True) as client:
        sources_by_bucket: dict[str, list[StartupHuntSourceConfig]] = {}
        for source in sources:
            sources_by_bucket.setdefault(_source_bucket(source), []).append(source)

        parallel_tasks: list[Any] = []
        parallel_indices: list[int] = []
        sequential_task_groups: list[Any] = []

        for bucket, bucket_sources in sources_by_bucket.items():
            if bucket in sequential_buckets and len(bucket_sources) > 1:
                sequential_task_groups.append(_per_bucket_sequential(bucket_sources))
            else:
                for src in bucket_sources:
                    parallel_indices.append(sources.index(src))
                    parallel_tasks.append(
                        _fetch_source_safe(client, src, payload, strategy, bucket_fatal=bucket_fatal)
                    )

        # Run parallel sources and sequential bucket groups concurrently.
        import asyncio as _aio

        all_jobs = [_aio.ensure_future(t) for t in parallel_tasks] + [
            _aio.ensure_future(g) for g in sequential_task_groups
        ]
        try:
            await _aio.wait(all_jobs, timeout=max(5.0, total_budget))
        except Exception:
            pass

        bucket_outputs: dict[int, dict[str, Any]] = {}
        # Parallel results
        for i, future in enumerate(all_jobs[: len(parallel_tasks)]):
            idx = parallel_indices[i]
            if future.done():
                try:
                    result = future.result()
                except Exception as exc:
                    msg = _scrub_error_message(f"{exc.__class__.__name__}: {exc}")
                    bucket_outputs[idx] = {"items": [], "error": msg}
                else:
                    bucket_outputs[idx] = result if isinstance(result, dict) else {"items": [], "error": "Invalid source response"}
            else:
                future.cancel()
                bucket_outputs[idx] = {"items": [], "error": "TimeoutError: source exceeded total search budget"}

        # Sequential bucket groups
        for future in all_jobs[len(parallel_tasks):]:
            if future.done():
                try:
                    group = future.result()
                except Exception:
                    group = []
                for idx, result in group or []:
                    bucket_outputs[idx] = result
            else:
                future.cancel()

        raw_results = [
            bucket_outputs.get(
                i,
                {"items": [], "error": "TimeoutError: source exceeded total search budget"},
            )
            for i in range(len(sources))
        ]

    results: list[dict[str, Any]] = []
    raw_bucket_counts: dict[str, int] = {bucket: 0 for bucket in SOURCE_BUCKETS}
    for source, report in zip(sources, raw_results):
        bucket = _source_bucket(source)
        items = report.get("items", [])
        raw_bucket_counts[bucket] = raw_bucket_counts.get(bucket, 0) + len(items)
        results.extend(items)

    results = await _enrich_opportunities_contacts(results)

    scored: list[dict[str, Any]] = []
    filtered_out: list[dict[str, Any]] = []
    for item in results:
        scored_item, filter_reason = _score_opportunity(item, payload, strategy, existing_opportunities)
        if scored_item is not None:
            scored.append(scored_item)
        elif filter_reason:
            filtered_out.append(
                {
                    "company_name": item.get("company_name"),
                    "role_title": item.get("role_title"),
                    "source_name": item.get("source_name"),
                    "source_bucket": _result_source_bucket(item),
                    "reason": filter_reason,
                }
            )

    deduped = _dedupe_opportunities(scored)
    if not deduped:
        relaxed_payload = _relax_search_payload(payload)
        relaxed_scored: list[dict[str, Any]] = []
        for item in results:
            scored_item, _ = _score_opportunity(item, relaxed_payload, strategy, existing_opportunities)
            if scored_item is not None:
                relaxed_scored.append(scored_item)
        deduped = _dedupe_opportunities(relaxed_scored)
    deduped.sort(key=lambda row: (-row["score_total"], row["rank_age_hours"], row["company_name"]))

    capped, source_result_counts = _apply_bucket_caps(deduped, payload)
    # Backfill counts for buckets that had raw items but were capped to zero accepted.
    for bucket in SOURCE_BUCKETS:
        source_result_counts.setdefault(bucket, 0)
    source_diagnostics = _build_source_diagnostics(payload, sources, raw_results, source_result_counts)

    effective_limit = _effective_result_limit(payload, sources)
    primary_results = capped[:effective_limit]
    overflow_results = capped[effective_limit:]
    return primary_results, overflow_results, filtered_out[:50], strategy, len(sources), source_result_counts, source_diagnostics


def _apply_bucket_caps(
    scored_results: list[dict[str, Any]],
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    bucket_usage: dict[str, int] = {bucket: 0 for bucket in SOURCE_BUCKETS}
    accepted: list[dict[str, Any]] = []
    for item in scored_results:
        bucket = item.get("source_bucket") or _result_source_bucket(item)
        limit = _bucket_limit(payload, bucket)
        if limit <= 0:
            continue
        if bucket_usage.get(bucket, 0) >= limit:
            continue
        bucket_usage[bucket] = bucket_usage.get(bucket, 0) + 1
        accepted.append(item)
    return accepted, bucket_usage


async def _gather(tasks: list[Any]) -> list[dict[str, Any]]:
    import asyncio

    settled = await asyncio.gather(*tasks, return_exceptions=True)
    output: list[dict[str, Any]] = []
    for item in settled:
        if isinstance(item, Exception):
            output.append({"items": [], "error": f"{item.__class__.__name__}: {item}"})
        else:
            output.append(item)
    return output


async def _gather_bucket_results(tasks: list[Any], budget_seconds: float) -> list[list[tuple[int, dict[str, Any]]]]:
    import asyncio

    futures = [asyncio.ensure_future(task) for task in tasks]
    try:
        await asyncio.wait(futures, timeout=max(5.0, budget_seconds))
    except Exception:
        pass

    output: list[list[tuple[int, dict[str, Any]]]] = []
    for future in futures:
        if future.done():
            try:
                result = future.result()
            except Exception:
                output.append([])
            else:
                output.append(result if isinstance(result, list) else [])
        else:
            future.cancel()
            output.append([])
    return output


async def _gather_with_budget(tasks: list[Any], budget_seconds: float) -> list[dict[str, Any]]:
    import asyncio

    futures = [asyncio.ensure_future(task) for task in tasks]
    try:
        await asyncio.wait(futures, timeout=max(5.0, budget_seconds))
    except Exception:
        pass

    output: list[dict[str, Any]] = []
    for future in futures:
        if future.done():
            try:
                result = future.result()
            except Exception as exc:
                output.append({"items": [], "error": f"{exc.__class__.__name__}: {exc}"})
            else:
                output.append(result if isinstance(result, dict) else {"items": [], "error": "Invalid source response"})
        else:
            future.cancel()
            output.append({"items": [], "error": "TimeoutError: source exceeded total search budget"})
    return output


_SECRET_QUERY_KEYS = {"token", "api_key", "apikey", "key", "auth", "access_token", "x-api-key"}
_BUCKET_FATAL_STATUSES = {401, 402, 403, 429}


def _scrub_url(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if not parsed.query:
        return url
    cleaned = [
        (key, "***" if key.lower() in _SECRET_QUERY_KEYS else value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunparse(parsed._replace(query=urlencode(cleaned)))


def _scrub_error_message(message: str) -> str:
    text = re.sub(r"https?://\S+", lambda m: _scrub_url(m.group(0)), message or "")
    text = re.sub(r"(token|api[_-]?key|apikey|access[_-]?token|authorization)=([^\s&'\"]+)", r"\1=***", text, flags=re.IGNORECASE)
    text = re.sub(r"apify_api_[A-Za-z0-9]+", "apify_api_***", text)
    return text


def _classify_bucket_fatal(exc: Exception) -> tuple[int | None, str | None]:
    """Return (status, friendly_reason) when the error means we should stop calling this bucket.

    `friendly_reason` is shown directly in the results UI, so it stays plain-
    language with no HTTP status codes or provider-internal error codes — the
    technical detail is logged server-side instead, for debugging.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in _BUCKET_FATAL_STATUSES:
            logger.warning(
                "Startup Hunt bucket source returned HTTP %s: %s",
                status,
                _scrub_error_message(exc.response.text[:500]),
            )
            if status == 402:
                return status, "This source's usage limit was reached. It's temporarily unavailable."
            if status == 401:
                return status, "This source's connection needs to be reconfigured. It's temporarily unavailable."
            if status == 403:
                return status, "This source declined the request. It's temporarily unavailable."
            if status == 429:
                return status, "This source is rate-limited right now. It'll be retried on your next search."
    return None, None


async def _fetch_source_safe(
    client: httpx.AsyncClient,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
    strategy: dict[str, Any],
    bucket_fatal: dict[str, str] | None = None,
) -> dict[str, Any]:
    bucket = _source_bucket(source)
    if bucket_fatal is not None and bucket in bucket_fatal:
        return {"items": [], "error": bucket_fatal[bucket]}
    try:
        items = await _fetch_source(client, source, payload, strategy)
        return {"items": items, "error": None}
    except Exception as exc:
        status, friendly = _classify_bucket_fatal(exc)
        if status and bucket_fatal is not None:
            reason = friendly or "This source is temporarily unavailable."
            bucket_fatal[bucket] = reason
            return {"items": [], "error": reason}
        logger.warning(
            "Startup Hunt source '%s' (%s) failed: %s",
            source.name, source.type, _scrub_error_message(f"{exc.__class__.__name__}: {exc}"),
        )
        return {"items": [], "error": "This source couldn't be reached right now."}


async def _fetch_source(
    client: httpx.AsyncClient,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    # Deferred imports (not at module top) - these provider modules import
    # shared helpers (normalize_text, StartupHuntSourceConfig, etc.) FROM
    # this module, so importing them back at engine.py's top would be a
    # circular import. By the time _fetch_source is actually called, this
    # module has finished loading and the cycle is a non-issue.
    if source.type == "greenhouse":
        from app.modules.startup_hunt.providers import greenhouse
        return await greenhouse.fetch(client, source) if greenhouse.is_available() else []
    if source.type == "lever":
        from app.modules.startup_hunt.providers import lever
        return await lever.fetch(client, source) if lever.is_available() else []
    if source.type == "ashby":
        from app.modules.startup_hunt.providers import ashby
        return await ashby.fetch(client, source) if ashby.is_available() else []
    if source.type == "startup_company":
        return await _fetch_startup_company(client, source, payload)
    if source.type == "startup_directory":
        return await _fetch_startup_directory(client, source, payload, strategy)
    if source.type == "google_web":
        from app.modules.startup_hunt.providers import google_web
        return await google_web.fetch(client, source, payload, strategy) if google_web.is_available() else []
    if source.type == "web_search":
        return await _fetch_web_search(client, source, payload, strategy)
    if source.type == "ats_discovery":
        return await _fetch_ats_discovery(client, source, payload, strategy)
    if source.type == "apify_actor":
        return await _fetch_apify_actor(client, source, payload, strategy)
    if source.type == "indeed_search":
        return await _fetch_indeed_search(client, source, payload, strategy)
    if source.type == "theirstack_search":
        from app.modules.startup_hunt.providers import theirstack
        return await theirstack.fetch(client, source, payload, strategy) if theirstack.is_available() else []
    return []


def _split_locations(payload: dict[str, Any]) -> list[str]:
    raw = str(payload.get("location") or "").strip()
    if not raw:
        return []
    parts = [part.strip() for part in re.split(r"[,;|/]+|\s+(?:and|or|und|oder)\s+", raw, flags=re.IGNORECASE) if part.strip()]
    seen: set[str] = set()
    locations: list[str] = []
    for part in parts:
        key = normalize_text(part)
        if not key or key in seen:
            continue
        seen.add(key)
        locations.append(part)
    return locations or [raw]


def _location_search_targets(payload: dict[str, Any], max_count: int = 6) -> list[str]:
    locations = _split_locations(payload)
    return locations[:max_count] if locations else [payload.get("location") or "Germany"]


def _auto_sources_from_integrations(payload: dict[str, Any]) -> list[StartupHuntSourceConfig]:
    sources: list[StartupHuntSourceConfig] = []
    location_targets = _location_search_targets(payload)

    if _bucket_enabled(payload, "web") and settings.google_cse_api_key and settings.google_cse_cx:
        sources.append(
            StartupHuntSourceConfig(
                type="google_web",
                name="Google Web Discovery",
                company="google-web",
                metadata={},
            )
        )
    if _bucket_enabled(payload, "apify") and payload.get("apify_limit", 0) > 0 and settings.apify_api_token and _is_supported_startup_actor(settings.apify_startup_hunt_actor_id):
        for location in location_targets:
            sources.append(
                StartupHuntSourceConfig(
                    type="apify_actor",
                    name=f"Apify Startup Discovery ({location})",
                    company="apify-startup",
                    metadata={"location": location},
                )
            )
    if _bucket_enabled(payload, "indeed") and payload.get("indeed_limit", 0) > 0 and settings.apify_api_token and settings.apify_indeed_actor_id:
        for location in location_targets:
            sources.append(
                StartupHuntSourceConfig(
                    type="indeed_search",
                    name=f"Indeed Discovery ({location})",
                    company="indeed",
                    metadata={"location": location},
                )
            )
    # No `and payload.get("theirstack_limit", 0) > 0` check here anymore -
    # that field no longer exists on the request (removed along with the
    # old per-request provider toggles), so it would always have evaluated
    # to 0 > 0 = False, silently disabling TheirStack regardless of
    # _bucket_enabled's value. _bucket_enabled(payload, "theirstack") is
    # config-driven now (see that function) and is the real gate.
    if _bucket_enabled(payload, "theirstack") and settings.theirstack_api_key:
        sources.append(
            StartupHuntSourceConfig(
                type="theirstack_search",
                name="TheirStack Discovery",
                company="theirstack",
                metadata={},
            )
        )
    return sources


def _auto_dynamic_sources(payload: dict[str, Any]) -> list[StartupHuntSourceConfig]:
    sources: list[StartupHuntSourceConfig] = []
    startupmap_url = _build_startupmap_url(payload.get("location"), payload.get("country"))
    if _bucket_enabled(payload, "startupmap") and payload.get("startupmap_limit", 0) > 0 and startupmap_url:
        sources.append(
            StartupHuntSourceConfig(
                type="startup_directory",
                name="StartupMap Dynamic",
                company="startupmap",
                url=startupmap_url,
                metadata={
                    "country": normalize_text(str(payload.get("country") or "germany")),
                    "city": normalize_text(str(payload.get("location") or "")) or "germany",
                    "company_link_patterns": ["/startups/"],
                    "english_friendly": True,
                    "default_stage": payload.get("company_stage") or "seed",
                    "dynamic_provider": "startupmap",
                },
            )
        )
    if _bucket_enabled(payload, "web") and payload.get("web_limit", 0) > 0:
        sources.append(
            StartupHuntSourceConfig(
                type="web_search",
                name="Web Discovery",
                company="web-search",
                metadata={"dynamic_provider": "web"},
            )
        )
    if _bucket_enabled(payload, "ats") and payload.get("ats_limit", 0) > 0:
        sources.append(
            StartupHuntSourceConfig(
                type="ats_discovery",
                name="ATS Discovery",
                company="ats-discovery",
                metadata={"dynamic_provider": "ats"},
            )
        )
    return sources


def _relax_search_payload(payload: dict[str, Any]) -> dict[str, Any]:
    relaxed = dict(payload)
    relaxed["company_stage"] = None
    relaxed["english_friendly_only"] = False
    relaxed["direct_links_only"] = False
    relaxed["remote_only"] = False
    relaxed["posted_within_hours"] = None
    return relaxed


def _source_bucket(source: StartupHuntSourceConfig) -> str:
    if source.type in {"greenhouse", "lever", "ashby", "ats_discovery"}:
        return "ats"
    if source.type == "indeed_search":
        return "indeed"
    if source.type == "theirstack_search":
        return "theirstack"
    if source.type == "apify_actor":
        return "apify"
    if source.type in {"google_web", "web_search"}:
        return "web"
    if source.type in {"startup_company", "startup_directory"}:
        if source.metadata.get("dynamic_provider") == "startupmap":
            return "startupmap"
        return "crawler"
    return "crawler"


def _result_source_bucket(item: dict[str, Any]) -> str:
    dynamic_provider = (item.get("company_payload") or {}).get("dynamic_provider")
    if dynamic_provider == "startupmap":
        return "startupmap"
    source_type = item.get("source_type")
    if source_type in {"greenhouse", "lever", "ashby", "ats_discovery"}:
        return "ats"
    if source_type == "indeed_search":
        return "indeed"
    if source_type == "theirstack_search":
        return "theirstack"
    if source_type == "apify_actor":
        return "apify"
    if source_type in {"google_web", "web_search"}:
        return "web"
    if source_type in {"startup_company", "startup_directory"}:
        return "crawler"
    return "crawler"


def _bucket_limit(payload: dict[str, Any], bucket: str) -> int:
    if not _bucket_enabled(payload, bucket):
        return 0
    # Fixed server-side caps for the buckets this refactor manages - mirrors
    # what used to be per-request *_limit fields, now config (see
    # config.py's "Startup Hunt — providers" section). Every other bucket
    # (crawler/startupmap/indeed/apify) isn't gated here at all anymore -
    # they resolve to 0 via _bucket_enabled below, same as their
    # always-off-in-practice behavior before this refactor.
    limits = {
        "ats": settings.startup_hunt_ats_result_limit,
        "theirstack": settings.startup_hunt_theirstack_result_limit,
        "web": settings.startup_hunt_google_web_result_limit,
    }
    return limits.get(bucket, 0)


def _bucket_enabled(payload: dict[str, Any], bucket: str) -> bool:
    # Server-side config decides whether a provider is allowed to run at
    # all now - the old per-request *_enabled booleans (and the "Provider
    # controls" UI that set them) are gone. "ats" is true if any of
    # greenhouse/lever/ashby is on (whichever's actually enabled still needs
    # this bucket's cap to be non-zero for its results to survive
    # _apply_bucket_caps). Every other bucket (crawler/startupmap/indeed/
    # apify) stays off - none of them had a working UI toggle before this
    # refactor either, so this isn't a behavior change for them.
    #
    # theirstack is the one exception that still reads `payload`:
    # service.py's DB-first shortfall check writes
    # payload["theirstack_enabled"] = False for one specific search when the
    # DB cache already covers it - that's not a user-facing toggle, it's an
    # internal "don't bother, DB already has enough" signal layered on top
    # of the config gate, not instead of it.
    if bucket == "theirstack":
        return settings.startup_hunt_theirstack_enabled and bool(payload.get("theirstack_enabled", True))
    flag_map = {
        "ats": settings.startup_hunt_greenhouse_enabled or settings.startup_hunt_lever_enabled or settings.startup_hunt_ashby_enabled,
        "web": settings.startup_hunt_google_web_enabled,
    }
    return flag_map.get(bucket, False)


def _bucket_available(payload: dict[str, Any], bucket: str) -> bool:
    if bucket == "crawler":
        return bool(payload.get("include_seeded_sources"))
    if bucket == "startupmap":
        return bool(_build_startupmap_url(payload.get("location"), payload.get("country")))
    if bucket == "web":
        return True
    if bucket == "indeed":
        return bool(settings.apify_api_token and settings.apify_indeed_actor_id)
    if bucket == "theirstack":
        return bool(settings.theirstack_api_key)
    if bucket == "apify":
        return bool(settings.apify_api_token and _is_supported_startup_actor(settings.apify_startup_hunt_actor_id))
    if bucket == "ats":
        return True
    return True


def _effective_result_limit(payload: dict[str, Any], sources: list[StartupHuntSourceConfig]) -> int:
    active_buckets = {_source_bucket(source) for source in sources}
    bucket_total = sum(_bucket_limit(payload, bucket) for bucket in active_buckets)
    requested_limit = int(payload.get("result_limit", 15) or 15)
    if bucket_total <= 0:
        return requested_limit
    return max(requested_limit, bucket_total)


def _build_source_diagnostics(
    payload: dict[str, Any],
    sources: list[StartupHuntSourceConfig],
    raw_results: list[dict[str, Any]],
    source_result_counts: dict[str, int] | None = None,
) -> dict[str, dict[str, Any]]:
    diagnostics: dict[str, dict[str, Any]] = {}
    source_result_counts = source_result_counts or {}
    sources_by_bucket: dict[str, list[StartupHuntSourceConfig]] = {}
    reports_by_bucket: dict[str, list[dict[str, Any]]] = {}
    for source, report in zip(sources, raw_results):
        bucket = _source_bucket(source)
        sources_by_bucket.setdefault(bucket, []).append(source)
        reports_by_bucket.setdefault(bucket, []).append(report)

    for bucket in SOURCE_BUCKETS:
        requested_limit = _bucket_limit(payload, bucket)
        bucket_sources = sources_by_bucket.get(bucket, [])
        bucket_reports = reports_by_bucket.get(bucket, [])
        configured = bool(bucket_sources)
        enabled = _bucket_enabled(payload, bucket)
        available = _bucket_available(payload, bucket)
        raw_count = sum(len(report.get("items", [])) for report in bucket_reports)
        accepted_count = int(source_result_counts.get(bucket, 0))
        errors = [str(report.get("error")) for report in bucket_reports if report.get("error")]
        status = "inactive"
        message = _inactive_bucket_reason(payload, bucket)
        if configured:
            if errors and accepted_count == 0 and raw_count == 0:
                status = "error"
                message = errors[0]
            elif accepted_count > 0:
                status = "ok"
                message = f"Accepted {accepted_count} results from {len(bucket_sources)} source(s)."
            elif raw_count > 0:
                status = "filtered"
                message = "Results were fetched but filtered out or displaced by the bucket cap."
            else:
                status = "empty"
                message = "Source ran but returned no results."

        diagnostics[bucket] = {
            "bucket": bucket,
            "requested_limit": requested_limit,
            "enabled": enabled,
            "available": available,
            "configured": configured,
            "active_sources": len(bucket_sources),
            "raw_count": raw_count,
            "accepted_count": accepted_count,
            "status": status,
            "message": message,
            "sources": [
                {
                    "name": source.name,
                    "type": source.type,
                    "error": report.get("error"),
                    "raw_count": len(report.get("items", [])),
                }
                for source, report in zip(bucket_sources, bucket_reports)
            ],
        }
    return diagnostics


def _inactive_bucket_reason(payload: dict[str, Any], bucket: str) -> str:
    if not _bucket_enabled(payload, bucket):
        return "Provider is disabled for this hunt."
    if _bucket_limit(payload, bucket) <= 0:
        return "Requested limit is 0."
    if bucket == "crawler" and not payload.get("include_seeded_sources"):
        return "Watchlist/crawler sources are off."
    if bucket == "startupmap":
        return "StartupMap source is not available for the selected location."
    if bucket == "web" and not (settings.google_cse_api_key and settings.google_cse_cx):
        return "Google CSE is not configured; runtime web search fallback will be used only when the source is added."
    if bucket == "indeed" and (not settings.apify_api_token or not settings.apify_indeed_actor_id):
        return "Indeed actor is not configured."
    if bucket == "theirstack" and not settings.theirstack_api_key:
        return "TheirStack API key is not configured."
    if bucket == "apify" and (not settings.apify_api_token or not _is_supported_startup_actor(settings.apify_startup_hunt_actor_id)):
        return "Startup Apify actor is not configured."
    if bucket == "ats":
        return "ATS discovery is enabled only when the ATS bucket is requested."
    return "Source is not active for this run."


def _limit_source_results(items: list[dict[str, Any]], source: StartupHuntSourceConfig, payload: dict[str, Any]) -> list[dict[str, Any]]:
    limit = _bucket_limit(payload, _source_bucket(source))
    if limit <= 0:
        return []
    return items[:limit]


def _is_supported_startup_actor(actor_id: str | None) -> bool:
    if not actor_id:
        return False
    normalized = actor_id.strip().lower()
    if not normalized:
        return False
    if "/" not in normalized and "~" not in normalized:
        return False
    # Generic browsing actors do not return the structured contract Startup Hunt expects.
    if normalized in {"apify/rag-web-browser", "rag-web-browser"}:
        return False
    if "linkedin-jobs-scraper" in normalized:
        return False
    return True


async def _fetch_startup_company(
    client: httpx.AsyncClient,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    company_payload = _base_company_payload(source)
    page_text = ""
    page_contacts: list[dict[str, Any]] = []
    careers_url = company_payload.get("company_careers_url")
    exact_job_url: str | None = None
    page_url = source.url or careers_url or company_payload.get("company_website_url")
    if page_url:
        try:
            html = await _fetch_html_with_optional_scrapling(client, page_url)
            page_text = _html_to_text(html)
            page_contacts = _contacts_from_page(html, company_payload.get("company_website_url") or page_url)
            if not careers_url:
                careers_url = _extract_careers_url(html, page_url)
                company_payload["company_careers_url"] = careers_url
            exact_job_url = _extract_matching_job_url(html, page_url, payload["query"])
            inferred = await _infer_company_metadata(page_text, source.company, payload["query"])
            company_payload = {**company_payload, **{k: v for k, v in inferred.items() if v is not None}}
        except Exception:
            pass

    contacts = _merge_contacts(_contacts_from_metadata(source.metadata, source.company), page_contacts)
    role = source.metadata.get("target_role") or payload["query"]
    opportunity_kind = "job" if exact_job_url else "outreach_lead"
    return [
        {
            "opportunity_kind": opportunity_kind,
            "company_name": source.company,
            "company_domain": extract_domain(company_payload.get("company_website_url")),
            "company_website_url": company_payload.get("company_website_url"),
            "company_careers_url": careers_url,
            "role_title": str(role),
            "location": company_payload.get("city") or company_payload.get("location") or "Germany",
            "country": company_payload.get("country"),
            "source_name": source.name,
            "source_type": source.type,
            "direct_apply_url": exact_job_url,
            "canonical_job_url": canonicalize_url(exact_job_url) if exact_job_url else None,
            "portal_job_url": source.url or careers_url,
            "posted_at": None,
            "company_payload": company_payload,
            "contacts": contacts,
            "raw_text": f"{source.company} {page_text}",
            "citation": {
                "source_name": source.name,
                "canonical_url": canonicalize_url(source.url) if source.url else (canonicalize_url(careers_url) if careers_url else ""),
                "job_url": careers_url or source.url or "",
                "posted_at": None,
                "evidence": ["Startup/company lead source configured for outbound discovery"],
                "extraction_note": "Used as a startup lead for founder or hiring-manager outreach even if no direct ATS posting was found.",
            },
        }
    ]


async def _fetch_startup_directory(
    client: httpx.AsyncClient,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    if not source.url:
        return []
    if "startupmap.one" in _source_host(source):
        html = await _fetch_startupmap_html(client, source.url, payload)
    else:
        html = await _fetch_html_with_optional_scrapling(client, source.url)
    directory_text = _html_to_text(html)
    if "startupmap.one" in _source_host(source):
        startup_entries = await _extract_startupmap_entries(html, source, payload, strategy)
    else:
        startup_entries = await _extract_startup_directory_entries(html, directory_text, source, payload, strategy)

    opportunities: list[dict[str, Any]] = []
    for entry in startup_entries:
        entry = await _enrich_directory_entry_detail(client, entry, payload)
        company_name = entry["company_name"]
        company_payload = {
            "stage": entry.get("stage") or source.metadata.get("default_stage"),
            "company_size": entry.get("company_size") or source.metadata.get("company_size"),
            "country": entry.get("country") or source.metadata.get("country"),
            "city": entry.get("city") or source.metadata.get("city"),
            "english_friendly": bool(entry.get("english_friendly") or source.metadata.get("english_friendly")),
            "ai_relevance": entry.get("ai_relevance") or source.metadata.get("ai_relevance") or entry.get("summary"),
            "relocation_support": entry.get("relocation_support") or source.metadata.get("relocation_support"),
            "company_website_url": entry.get("company_website_url"),
            "company_careers_url": entry.get("company_careers_url"),
            "source_tags": entry.get("tags", []),
            "dynamic_provider": source.metadata.get("dynamic_provider"),
        }
        contacts = _merge_contacts(
            entry.get("contacts", []),
            _contacts_from_page(entry.get("detail_html", ""), entry.get("detail_url") or source.url),
        )
        opportunity_kind = "job" if company_payload.get("company_careers_url") else "outreach_lead"
        opportunities.append(
            {
                "opportunity_kind": opportunity_kind,
                "company_name": company_name,
                "company_domain": extract_domain(company_payload.get("company_website_url")),
                "company_website_url": company_payload.get("company_website_url"),
                "company_careers_url": company_payload.get("company_careers_url"),
                "role_title": entry.get("target_role") or payload["query"],
                "location": entry.get("city") or company_payload.get("city") or "Germany",
                "country": company_payload.get("country"),
                "source_name": source.name,
                "source_type": source.type,
                "direct_apply_url": company_payload.get("company_careers_url"),
                "canonical_job_url": canonicalize_url(company_payload["company_careers_url"]) if company_payload.get("company_careers_url") else None,
                "portal_job_url": entry.get("detail_url"),
                "posted_at": None,
                "company_payload": company_payload,
                "contacts": contacts,
                "raw_text": f'{company_name} {entry.get("summary", "")} {entry.get("tags_text", "")}',
                "citation": {
                    "source_name": source.name,
                    "canonical_url": canonicalize_url(entry.get("detail_url") or source.url),
                    "job_url": entry.get("detail_url") or source.url,
                    "posted_at": None,
                    "evidence": ["Startup directory lead matched your AI/ML Germany strategy"],
                    "extraction_note": "Directory-sourced startup lead surfaced for hidden-gem discovery and outreach.",
                },
            }
        )
    return opportunities


async def _enrich_directory_entry_detail(
    client: httpx.AsyncClient,
    entry: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    detail_url = entry.get("detail_url")
    if not detail_url:
        return entry

    try:
        html = await _fetch_html_with_optional_scrapling(client, detail_url)
    except Exception:
        return entry

    page_text = _html_to_text(html)
    company_website_url = entry.get("company_website_url") or _extract_company_website_url(html, detail_url)
    company_careers_url = entry.get("company_careers_url") or _extract_careers_url(html, company_website_url or detail_url)
    contacts = _merge_contacts(entry.get("contacts", []), _contacts_from_page(html, company_website_url or detail_url))
    inferred = await _infer_company_metadata(page_text, entry.get("company_name", ""), payload["query"])

    enriched = dict(entry)
    enriched["detail_html"] = html
    enriched["company_website_url"] = company_website_url
    enriched["company_careers_url"] = company_careers_url
    enriched["contacts"] = contacts
    enriched["summary"] = entry.get("summary") or page_text[:280]
    for key in ("stage", "company_size", "city", "country", "ai_relevance", "relocation_support"):
        if not enriched.get(key) and inferred.get(key):
            enriched[key] = inferred[key]
    if inferred.get("english_friendly") is not None and not enriched.get("english_friendly"):
        enriched["english_friendly"] = inferred["english_friendly"]
    return enriched


async def _extract_startupmap_entries(
    html: str,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    entries = _extract_startupmap_from_next_data(html, source, payload)
    if entries:
        filtered = _filter_startupmap_entries(entries, payload, strategy)
        return filtered or _fallback_startupmap_entries(entries)

    entries = _extract_startupmap_from_links(html, source, payload)
    if entries:
        filtered = _filter_startupmap_entries(entries, payload, strategy)
        return filtered or _fallback_startupmap_entries(entries)

    return await _extract_directory_candidates_via_ai(_html_to_text(html), source, payload, strategy)


def _extract_startupmap_from_next_data(
    html: str,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, flags=re.I | re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    objects = list(_walk_json_objects(data))
    entries: list[dict[str, Any]] = []
    for obj in objects:
        name = _first_present(obj, ["name", "title", "companyName"])
        slug = _first_present(obj, ["slug", "path"])
        website = _first_present(obj, ["website", "websiteUrl", "companyWebsite", "externalWebsite"])
        city = _first_present(obj, ["city", "location", "hqCity"])
        country = _first_present(obj, ["country", "hqCountry"])
        stage = _first_present(obj, ["stage", "fundingStage"])
        summary = _first_present(obj, ["shortDescription", "description", "tagline", "summary"])
        tags = obj.get("tags") if isinstance(obj.get("tags"), list) else obj.get("industries") if isinstance(obj.get("industries"), list) else []
        if not isinstance(name, str) or not name.strip():
            continue
        if slug and isinstance(slug, str) and slug.startswith("/"):
            detail_url = urljoin(source.url or "", slug)
        elif isinstance(slug, str) and slug:
            detail_url = urljoin(source.url or "", f"/startups/{slug}")
        else:
            detail_url = None
        if detail_url:
            detail_url = canonicalize_url(detail_url)
        website_url = website if isinstance(website, str) and website.startswith("http") and _is_probable_company_url(website, source.url) else None
        entry = {
            "company_name": str(name).strip(),
            "detail_url": detail_url,
            "summary": str(summary).strip() if isinstance(summary, str) and summary.strip() else None,
            "city": str(city).strip() if isinstance(city, str) and city.strip() else source.metadata.get("city"),
            "country": str(country).strip() if isinstance(country, str) and country.strip() else source.metadata.get("country"),
            "stage": str(stage).strip() if isinstance(stage, str) and stage.strip() else source.metadata.get("default_stage"),
            "tags": [str(tag).strip() for tag in tags if str(tag).strip()] if isinstance(tags, list) else [],
            "tags_text": " ".join([str(tag).strip() for tag in tags if str(tag).strip()]) if isinstance(tags, list) else "",
            "ai_relevance": str(summary).strip() if isinstance(summary, str) and summary.strip() else None,
            "target_role": payload["query"],
            "company_website_url": website_url,
            "company_careers_url": None,
            "contacts": [],
            "detail_html": "",
        }
        entries.append(entry)
    return _dedupe_directory_entries(entries)


def _extract_startupmap_from_links(
    html: str,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    pattern = re.compile(r'<a[^>]+href=["\']([^"\']*/startups/[^"\']+)["\'][^>]*>(.*?)</a>', flags=re.I | re.S)
    entries: list[dict[str, Any]] = []
    for href, inner_html in pattern.findall(html):
        detail_url = canonicalize_url(urljoin(source.url or "", href))
        label = _html_to_text(inner_html)
        if not label:
            continue
        entries.append(
            {
                "company_name": label,
                "detail_url": detail_url,
                "summary": None,
                "city": source.metadata.get("city"),
                "country": source.metadata.get("country"),
                "stage": source.metadata.get("default_stage"),
                "tags": [],
                "tags_text": "",
                "ai_relevance": None,
                "target_role": payload["query"],
                "company_website_url": None,
                "company_careers_url": None,
                "contacts": [],
                "detail_html": "",
            }
        )
    return _dedupe_directory_entries(entries)


def _filter_startupmap_entries(
    entries: list[dict[str, Any]],
    payload: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    query_tokens = tokenize(payload["query"])
    preferred_cities = {normalize_text(city) for city in strategy.get("preferred_cities", []) if city}
    filtered: list[dict[str, Any]] = []
    for entry in entries:
        haystack = normalize_text(
            " ".join(
                [
                    entry.get("company_name") or "",
                    entry.get("summary") or "",
                    entry.get("tags_text") or "",
                    entry.get("city") or "",
                    entry.get("country") or "",
                ]
            )
        )
        stage_text = normalize_text(entry.get("stage") or "")
        city_text = normalize_text(entry.get("city") or "")
        if query_tokens and not any(token in haystack for token in query_tokens):
            ai_hint = any(term in haystack for term in ["ai", "ml", "machine learning", "llm", "data", "model"])
            if not ai_hint:
                continue
        desired_stage = normalize_text(payload.get("company_stage") or strategy.get("company_stage") or "")
        if desired_stage and desired_stage not in stage_text:
            continue
        if preferred_cities and city_text and city_text not in preferred_cities and "germany" not in preferred_cities:
            continue
        filtered.append(entry)
    return filtered[:20]


def _fallback_startupmap_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prioritized: list[dict[str, Any]] = []
    for entry in entries:
        haystack = normalize_text(
            " ".join(
                [
                    entry.get("company_name") or "",
                    entry.get("summary") or "",
                    entry.get("tags_text") or "",
                ]
            )
        )
        if any(term in haystack for term in ["ai", "ml", "machine learning", "llm", "data", "model"]):
            prioritized.append(entry)
    return (prioritized or entries)[:20]


def _walk_json_objects(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_json_objects(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_json_objects(nested)


def _first_present(obj: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = obj.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _dedupe_directory_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for entry in entries:
        raw_key = entry.get("detail_url") or entry.get("company_website_url") or entry["company_name"]
        key = canonicalize_url(raw_key) if isinstance(raw_key, str) and raw_key.startswith("http") else normalize_text(str(raw_key))
        current = deduped.get(key)
        if current is None or len(entry.get("summary") or "") > len(current.get("summary") or ""):
            deduped[key] = entry
    return list(deduped.values())


async def _fetch_web_search(
    client: httpx.AsyncClient,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    query = _build_web_query(payload, strategy)
    target = max(int(payload.get("web_limit", 0) or 0), int(payload.get("result_limit", 15) or 15))
    cse_matches = await _google_cse_search_matches(client, query, target * 2)
    if cse_matches:
        matches = _filter_search_matches(cse_matches, mode="web")
    else:
        html = await _search_html(client, query)
        matches = _filter_search_matches(_parse_search_results(html), mode="web")
    if not matches:
        return await _fallback_company_page_discovery(client, payload, strategy, mode="web")
    opportunities: list[dict[str, Any]] = []
    raw_cap = max(payload.get("web_limit", 0), payload.get("result_limit", 15))
    for match in matches[: max(raw_cap, raw_cap * 2)]:
        link = match["url"]
        title = match["title"]
        snippet = match["snippet"]
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
            "company_careers_url": link if any(token in link.lower() for token in ["/careers", "/jobs", "greenhouse.io", "lever.co", "ashbyhq.com"]) else None,
            "source_tags": ["web-search"],
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
                    "evidence": ["Discovered via runtime web search"],
                    "extraction_note": "Runtime web discovery found a startup or careers lead from public search results.",
                },
            }
        )
    return opportunities


async def _fetch_ats_discovery(
    client: httpx.AsyncClient,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    query = _build_ats_query(payload, strategy)
    target = max(int(payload.get("ats_limit", 0) or 0), int(payload.get("result_limit", 15) or 15))
    cse_matches = await _google_cse_search_matches(client, query, target * 2)
    if cse_matches:
        matches = _filter_search_matches(cse_matches, mode="ats")
    else:
        html = await _search_html(client, query)
        matches = _filter_search_matches(_parse_search_results(html), mode="ats")
    if not matches:
        return await _fallback_company_page_discovery(client, payload, strategy, mode="ats")
    opportunities: list[dict[str, Any]] = []
    ats_cap = max(payload.get("ats_limit", 0), payload.get("result_limit", 15))
    for match in matches[: max(ats_cap, ats_cap * 2)]:
        link = match["url"]
        title = match["title"]
        snippet = match["snippet"]
        company_name = _infer_company_from_search_result(title, link)
        role_title = _role_title_from_search_result(title, payload["query"])
        company_payload = {
            "stage": None,
            "company_size": None,
            "country": payload.get("country"),
            "city": payload.get("location"),
            "english_friendly": "english" in normalize_text(snippet),
            "ai_relevance": snippet,
            "relocation_support": None,
            "company_website_url": _root_url(link),
            "company_careers_url": link,
            "source_tags": ["ats-discovery"],
        }
        opportunities.append(
            {
                "opportunity_kind": "job",
                "company_name": company_name,
                "company_domain": extract_domain(link),
                "company_website_url": company_payload["company_website_url"],
                "company_careers_url": company_payload["company_careers_url"],
                "role_title": role_title,
                "location": payload["location"],
                "country": payload.get("country"),
                "source_name": source.name,
                "source_type": source.type,
                "direct_apply_url": link,
                "canonical_job_url": canonicalize_url(link),
                "portal_job_url": None,
                "posted_at": None,
                "company_payload": company_payload,
                "contacts": [],
                "raw_text": f"{title} {snippet}",
                "citation": {
                    "source_name": source.name,
                    "canonical_url": canonicalize_url(link),
                    "job_url": link,
                    "posted_at": None,
                    "evidence": ["Discovered via runtime ATS search"],
                    "extraction_note": "Runtime ATS discovery found a direct careers or apply page on a public ATS host.",
                },
            }
        )
    return opportunities


async def _fallback_company_page_discovery(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
    strategy: dict[str, Any],
    mode: str,
) -> list[dict[str, Any]]:
    startupmap_url = _build_startupmap_url(payload.get("location"), payload.get("country"))
    if not startupmap_url:
        return []

    source = StartupHuntSourceConfig(
        type="startup_directory",
        name="StartupMap Fallback",
        company="startupmap-fallback",
        url=startupmap_url,
        metadata={
            "country": normalize_text(str(payload.get("country") or "germany")),
            "city": normalize_text(str(payload.get("location") or "")) or "germany",
            "company_link_patterns": ["/startups/"],
            "english_friendly": True,
            "default_stage": payload.get("company_stage") or "seed",
            "dynamic_provider": "startupmap",
        },
    )
    try:
        html = await _fetch_startupmap_html(client, startupmap_url, payload)
        entries = await _extract_startupmap_entries(html, source, payload, strategy)
    except Exception:
        return []

    opportunities: list[dict[str, Any]] = []
    limit = max(1, int(payload.get(f"{mode}_limit", 0) or payload.get("result_limit", 15) or 15))
    for raw_entry in entries[:limit * 2]:
        entry = await _enrich_directory_entry_detail(client, dict(raw_entry), payload)
        detail_url = entry.get("detail_url")
        company_website_url = _safe_company_website_url(entry.get("company_website_url"))
        company_careers_url = entry.get("company_careers_url")
        emitted = False
        page_urls = [url for url in [company_careers_url, company_website_url, detail_url] if url]
        for page_url in page_urls:
            try:
                page_html = await _fetch_html_with_optional_scrapling(client, page_url)
            except Exception:
                continue
            if not company_careers_url:
                company_careers_url = _extract_careers_url(page_html, page_url)
            if not company_website_url:
                company_website_url = _safe_company_website_url(_extract_company_website_url(page_html, page_url))
            if mode == "ats" and company_careers_url and _is_ats_url(company_careers_url):
                opportunities.append(
                    _build_runtime_discovery_opportunity(
                        payload=payload,
                        entry=entry,
                        source_name="ATS Discovery",
                        source_type="ats_discovery",
                        company_website_url=company_website_url,
                        company_careers_url=company_careers_url,
                        portal_job_url=detail_url or company_careers_url,
                        snippet=(entry.get("summary") or ""),
                    )
                )
                emitted = True
                break
            if mode == "web":
                opportunities.append(
                    _build_runtime_discovery_opportunity(
                        payload=payload,
                        entry=entry,
                        source_name="Web Discovery",
                        source_type="web_search",
                        company_website_url=company_website_url,
                        company_careers_url=company_careers_url,
                        portal_job_url=detail_url or company_website_url or company_careers_url,
                        snippet=(entry.get("summary") or ""),
                    )
                )
                emitted = True
                break
        if mode == "web" and not emitted and (detail_url or company_website_url or company_careers_url):
            opportunities.append(
                _build_runtime_discovery_opportunity(
                    payload=payload,
                    entry=entry,
                    source_name="Web Discovery",
                    source_type="web_search",
                    company_website_url=company_website_url,
                    company_careers_url=company_careers_url,
                    portal_job_url=detail_url or company_website_url or company_careers_url,
                    snippet=(entry.get("summary") or ""),
                )
            )
        if len(opportunities) >= limit:
            break
    return opportunities[:limit]


async def _fetch_startupmap_html(client: httpx.AsyncClient, startupmap_url: str, payload: dict[str, Any]) -> str:
    import asyncio

    candidate_urls = [startupmap_url]
    root_url = "https://startupmap.one/startups"
    country_url = _build_startupmap_url(None, payload.get("country"))
    for candidate in [root_url, country_url]:
        if candidate and candidate not in candidate_urls:
            candidate_urls.append(candidate)

    last_exc: Exception | None = None
    for candidate_url in candidate_urls:
        for _ in range(2):
            try:
                return await _fetch_html_with_optional_scrapling(client, candidate_url)
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in {429, 500, 502, 503, 504}:
                    raise
                await asyncio.sleep(1.5)
            except Exception as exc:
                last_exc = exc
                break
    if last_exc:
        raise last_exc
    raise RuntimeError("StartupMap fetch failed without an explicit exception")


def _build_runtime_discovery_opportunity(
    payload: dict[str, Any],
    entry: dict[str, Any],
    source_name: str,
    source_type: str,
    company_website_url: str | None,
    company_careers_url: str | None,
    portal_job_url: str | None,
    snippet: str,
) -> dict[str, Any]:
    company_payload = {
        "stage": entry.get("stage"),
        "company_size": entry.get("company_size"),
        "country": entry.get("country") or payload.get("country"),
        "city": entry.get("city") or payload.get("location"),
        "english_friendly": bool(entry.get("english_friendly")),
        "ai_relevance": entry.get("ai_relevance") or snippet,
        "relocation_support": entry.get("relocation_support"),
        "company_website_url": company_website_url,
        "company_careers_url": company_careers_url,
        "source_tags": entry.get("tags", []),
        "dynamic_provider": entry.get("dynamic_provider"),
    }
    return {
        "opportunity_kind": "job" if company_careers_url else "outreach_lead",
        "company_name": entry.get("company_name") or "Startup lead",
        "company_domain": extract_domain(company_website_url or company_careers_url or portal_job_url),
        "company_website_url": company_website_url,
        "company_careers_url": company_careers_url,
        "role_title": payload["query"],
        "location": entry.get("city") or payload.get("location") or "Germany",
        "country": entry.get("country") or payload.get("country"),
        "source_name": source_name,
        "source_type": source_type,
        "direct_apply_url": company_careers_url,
        "canonical_job_url": canonicalize_url(company_careers_url) if company_careers_url else None,
        "portal_job_url": portal_job_url,
        "posted_at": None,
        "company_payload": company_payload,
        "contacts": entry.get("contacts", []),
        "raw_text": f'{payload["query"]} {entry.get("company_name") or ""} {snippet}',
        "citation": {
            "source_name": source_name,
            "canonical_url": canonicalize_url(portal_job_url) if portal_job_url else "",
            "job_url": company_careers_url or portal_job_url or "",
            "posted_at": None,
            "evidence": ["Recovered via company-page fallback discovery"],
            "extraction_note": "Fallback discovery inspected startup pages directly when search-engine result parsing returned nothing.",
        },
    }


async def _fetch_apify_actor(
    client: httpx.AsyncClient,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    actor_id = source.metadata.get("actor_id") or settings.apify_startup_hunt_actor_id
    if not settings.apify_api_token or not actor_id:
        return []
    contract = str(source.metadata.get("actor_output_type") or "").strip().lower()
    source_payload = dict(payload)
    if source.metadata.get("location"):
        source_payload["__source_location"] = source.metadata["location"]
    if _is_startup_jobs_intelligence_actor(actor_id):
        try:
            items = await _run_apify_actor(
                client,
                actor_id,
                _startup_jobs_intelligence_input(source_payload, strategy, minimal=False),
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 400:
                raise
            items = await _run_apify_actor(
                client,
                actor_id,
                _startup_jobs_intelligence_input(source_payload, strategy, minimal=True),
            )
        return _normalize_apify_items(
            items,
            source.name,
            source.type,
            payload,
            contract or "startup_jobs_intelligence_v1",
        )
    run_input = {
        "query": payload["query"],
        "queries": _ai_engineer_family_variants(payload["query"])[:6],
        "location": payload["location"],
        "country": payload.get("country"),
        "strategy": strategy,
        "limit": payload.get("result_limit", 15),
    }
    items = await _run_apify_actor(client, actor_id, run_input)
    return _normalize_apify_items(items, source.name, source.type, payload, contract or "startup_hunt_v1")


async def _fetch_indeed_search(
    client: httpx.AsyncClient,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    actor_id = source.metadata.get("actor_id") or settings.apify_indeed_actor_id
    if not settings.apify_api_token or not actor_id:
        return []
    result_limit = max(1, int(payload.get("indeed_limit", 0) or payload.get("result_limit", 15) or 15))
    variants = _ai_engineer_family_variants(payload["query"])[:6]
    title_query = " OR ".join(f'"{v}"' for v in variants) if variants else payload["query"]
    search_location = source.metadata.get("location") or payload["location"]
    is_remote_location = "remote" in normalize_text(str(search_location))
    run_input: dict[str, Any] = {
        "title": title_query,
        "location": search_location,
        "country": _country_code_for_indeed(payload.get("country")),
        "limit": result_limit,
        "datePosted": _indeed_date_posted(payload.get("posted_within_hours")),
    }
    if is_remote_location:
        run_input["remoteOnly"] = True
        run_input["remote"] = True
    items = await _run_apify_actor(client, actor_id, run_input)
    contract = str(source.metadata.get("actor_output_type") or "indeed_v1").strip().lower()
    return _normalize_apify_items(items, source.name, source.type, payload, contract)


async def _fetch_html_with_optional_scrapling(client: httpx.AsyncClient, url: str) -> str:
    try:
        from scrapling.fetchers import AsyncFetcher

        fetcher = AsyncFetcher(auto_match=True)
        result = await fetcher.get(url)
        html = getattr(result, "html", None) or getattr(result, "text", None)
        if html:
            return str(html)
    except Exception:
        pass

    response = await client.get(url)
    response.raise_for_status()
    return response.text


async def _run_apify_actor(client: httpx.AsyncClient, actor_id: str, run_input: dict[str, Any]) -> list[dict[str, Any]]:
    import asyncio

    base = settings.apify_base_url.rstrip("/")
    token = settings.apify_api_token
    actor_ref = _normalize_apify_actor_id(actor_id)
    start_res = await client.post(
        f"{base}/acts/{actor_ref}/runs",
        params={"token": token},
        json=run_input,
    )
    start_res.raise_for_status()
    run_data = start_res.json().get("data", {})
    run_id = run_data.get("id")
    dataset_id = run_data.get("defaultDatasetId")
    if not dataset_id:
        return []

    status = str(run_data.get("status") or "").upper()
    max_wait_seconds = max(30, int(getattr(settings, "startup_hunt_apify_poll_seconds", 120)))
    elapsed = 0.0
    delay = 2.0
    while status not in APIFY_TERMINAL_STATUSES and elapsed < max_wait_seconds:
        await asyncio.sleep(delay)
        elapsed += delay
        delay = min(delay * 1.4, 8.0)
        if not run_id:
            continue
        run_res = await client.get(
            f"{base}/actor-runs/{run_id}",
            params={"token": token},
        )
        run_res.raise_for_status()
        run_data = run_res.json().get("data", {}) or run_data
        status = str(run_data.get("status") or "").upper()

    if status and status != "SUCCEEDED":
        return []

    items_res = await client.get(
        f"{base}/datasets/{dataset_id}/items",
        params={"token": token, "clean": "true"},
    )
    items_res.raise_for_status()
    data = items_res.json()
    return data if isinstance(data, list) else []


def _normalize_apify_items(
    items: list[dict[str, Any]],
    source_name: str,
    source_type: str,
    payload: dict[str, Any],
    contract: str,
) -> list[dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    base_limit = max(1, int(payload.get("apify_limit", 0) or payload.get("result_limit", 15) or 15))
    limit = min(base_limit * 3, 60)
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        mapped = _map_apify_item(item, contract, payload)
        url = mapped["url"]
        title = mapped["title"]
        company_name = mapped["company_name"]
        if not url and not company_name:
            continue
        location = mapped["location"]
        snippet = mapped["snippet"]
        company_payload = {
            "stage": mapped["stage"],
            "company_size": mapped["company_size"],
            "country": mapped["country"] or payload.get("country"),
            "city": mapped["city"] or payload.get("location"),
            "english_friendly": mapped["english_friendly"],
            "ai_relevance": mapped["ai_relevance"] or snippet,
            "relocation_support": mapped["relocation_support"],
            "company_website_url": _safe_company_website_url(mapped["company_website_url"]) or _root_url(url),
            "company_careers_url": mapped["company_careers_url"] or (url if any(token in url.lower() for token in ["/careers", "/jobs", "greenhouse.io", "lever.co"]) else None),
            "source_tags": mapped["tags"],
        }
        contacts = []
        if isinstance(mapped["contacts"], list):
            for contact in mapped["contacts"]:
                if isinstance(contact, dict):
                    contacts.append(
                        {
                            "name": str(contact.get("name", "")).strip(),
                            "title": str(contact.get("title", "")).strip() or "Contact",
                            "contact_type": _infer_contact_type(str(contact.get("title", ""))),
                            "email": str(contact.get("email", "")).strip() or None,
                            "email_confidence": str(contact.get("email_confidence", "")).strip() or ("high" if contact.get("email") else "unknown"),
                            "linkedin_url": str(contact.get("linkedin_url", "")).strip() or None,
                            "source": source_name,
                            "provider_chain": [source_name],
                        }
                    )
        opportunities.append(
            {
                "opportunity_kind": "job" if company_payload["company_careers_url"] else "outreach_lead",
                "company_name": company_name,
                "company_domain": extract_domain(company_payload["company_website_url"] or url),
                "company_website_url": company_payload["company_website_url"],
                "company_careers_url": company_payload["company_careers_url"],
                "role_title": title,
                "location": location,
                "country": company_payload["country"],
                "source_name": source_name,
                "source_type": source_type,
                "direct_apply_url": company_payload["company_careers_url"],
                "canonical_job_url": canonicalize_url(company_payload["company_careers_url"]) if company_payload["company_careers_url"] else None,
                "portal_job_url": url or None,
                "posted_at": parse_dt(str(mapped["posted_at"] or "")),
                "company_payload": company_payload,
                "contacts": contacts,
                "raw_text": f"{title} {company_name} {snippet}",
                "citation": {
                    "source_name": source_name,
                    "canonical_url": canonicalize_url(url) if url else "",
                    "job_url": url,
                    "posted_at": mapped["posted_at"],
                    "evidence": [f"Discovered via {source_name}", f"Apify contract: {contract}"],
                    "extraction_note": "Result imported from Apify-powered discovery.",
                },
            }
        )
    return opportunities


def _map_apify_item(item: dict[str, Any], contract: str, payload: dict[str, Any]) -> dict[str, Any]:
    if contract == "indeed_v1":
        employer = item.get("employer") if isinstance(item.get("employer"), dict) else {}
        location_obj = item.get("location") if isinstance(item.get("location"), dict) else {}
        description_obj = item.get("description") if isinstance(item.get("description"), dict) else {}
        company_name = str(item.get("companyName") or item.get("company") or employer.get("name") or "").strip()
        title = str(item.get("title") or item.get("jobTitle") or payload["query"]).strip()
        url = str(item.get("jobUrl") or item.get("url") or item.get("link") or "").strip()
        location = str(
            item.get("jobLocation")
            or item.get("locationText")
            or ", ".join([part for part in [location_obj.get("city"), location_obj.get("countryName")] if part])
            or payload["location"]
        ).strip()
        return {
            "url": url,
            "title": title,
            "company_name": company_name or _infer_company_from_search_result(title, url),
            "location": location,
            "snippet": str(item.get("snippet") or item.get("summary") or description_obj.get("text") or item.get("description") or "").strip(),
            "stage": item.get("stage"),
            "company_size": item.get("companySize") or item.get("company_size") or employer.get("employeesCount"),
            "country": item.get("country") or location_obj.get("countryName") or location_obj.get("countryCode"),
            "city": item.get("city") or location_obj.get("city"),
            "english_friendly": bool(item.get("englishFriendly") or item.get("english_friendly") or item.get("language") == "en"),
            "ai_relevance": item.get("ai_relevance"),
            "relocation_support": item.get("relocation_support"),
            "company_website_url": _safe_company_website_url(item.get("companyWebsite") or item.get("company_website_url") or employer.get("corporateWebsite")),
            "company_careers_url": item.get("applyUrl") or item.get("company_careers_url"),
            "tags": item.get("tags") or [],
            "contacts": item.get("contacts") or [],
            "posted_at": item.get("datePosted") or item.get("datePublished") or item.get("posted_at"),
        }
    if contract == "startup_jobs_intelligence_v1":
        company_obj = item.get("company") if isinstance(item.get("company"), dict) else {}
        startup_obj = item.get("startup") if isinstance(item.get("startup"), dict) else {}
        effective_company = company_obj or startup_obj
        company_name = str(
            item.get("companyName")
            or item.get("company_name")
            or effective_company.get("name")
            or item.get("company")
            or ""
        ).strip()
        title = str(item.get("title") or item.get("role") or item.get("jobTitle") or payload["query"]).strip()
        url = str(
            item.get("applyUrl")
            or item.get("jobUrl")
            or item.get("postingUrl")
            or item.get("url")
            or item.get("link")
            or ""
        ).strip()
        description = str(
            item.get("description")
            or item.get("summary")
            or item.get("snippet")
            or item.get("whyNow")
            or ""
        ).strip()
        tags = item.get("techStack") if isinstance(item.get("techStack"), list) else item.get("tags") or []
        return {
            "url": url,
            "title": title,
            "company_name": company_name or _infer_company_from_search_result(title, url),
            "location": str(
                item.get("location")
                or item.get("city")
                or effective_company.get("location")
                or payload["location"]
            ).strip(),
            "snippet": description,
            "stage": (
                _humanize_theirstack_stage(item.get("fundingStage"))
                or _humanize_theirstack_stage(item.get("stage"))
                or _humanize_theirstack_stage(effective_company.get("fundingStage"))
            ),
            "company_size": (
                _humanize_employee_count(item.get("companySize"))
                or _humanize_employee_count(item.get("teamSize"))
                or _humanize_employee_count(effective_company.get("employeeCount"))
                or _humanize_employee_count(effective_company.get("companySize"))
            ),
            "country": item.get("country") or effective_company.get("country") or payload.get("country"),
            "city": item.get("city") or effective_company.get("city"),
            "english_friendly": bool(
                item.get("englishFriendly")
                or item.get("english_friendly")
                or "english" in normalize_text(description)
            ),
            "ai_relevance": item.get("ai_relevance") or description or " ".join(str(tag) for tag in tags),
            "relocation_support": item.get("relocation_support") or item.get("relocation") or effective_company.get("relocationSupport"),
            "company_website_url": _safe_company_website_url(
                item.get("companyWebsite")
                or effective_company.get("website")
                or effective_company.get("domain")
            ),
            "company_careers_url": item.get("careersUrl") or item.get("applyUrl") or item.get("jobUrl"),
            "tags": tags,
            "contacts": item.get("contacts") or [],
            "posted_at": item.get("postedAt") or item.get("datePosted") or item.get("posted_at"),
        }

    company_name = str(item.get("company") or item.get("companyName") or "").strip()
    title = str(item.get("title") or item.get("jobTitle") or payload["query"]).strip()
    url = str(item.get("url") or item.get("jobUrl") or item.get("link") or "").strip()
    return {
        "url": url,
        "title": title,
        "company_name": company_name or _infer_company_from_search_result(title, url),
        "location": str(item.get("location") or item.get("city") or payload["location"]).strip(),
        "snippet": str(item.get("description") or item.get("snippet") or item.get("summary") or "").strip(),
        "stage": item.get("stage"),
        "company_size": item.get("company_size") or item.get("companySize"),
        "country": item.get("country"),
        "city": item.get("city"),
        "english_friendly": bool(item.get("english_friendly") or item.get("englishFriendly")),
        "ai_relevance": item.get("ai_relevance"),
        "relocation_support": item.get("relocation_support"),
        "company_website_url": item.get("company_website_url") or item.get("companyWebsite"),
        "company_careers_url": item.get("company_careers_url") or item.get("applyUrl"),
        "tags": item.get("tags") or [],
        "contacts": item.get("contacts") or [],
        "posted_at": item.get("posted_at") or item.get("datePosted"),
    }


async def _google_cse_search_matches(client: httpx.AsyncClient, query: str, target: int) -> list[dict[str, str]]:
    if not settings.google_cse_api_key or not settings.google_cse_cx:
        return []
    target = max(1, min(target, 30))
    out: list[dict[str, str]] = []
    start = 1
    while len(out) < target and start <= 91:
        try:
            response = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": settings.google_cse_api_key,
                    "cx": settings.google_cse_cx,
                    "q": query,
                    "num": min(10, target - len(out)),
                    "start": start,
                },
            )
            if response.status_code in (400, 429):
                break
            response.raise_for_status()
        except Exception:
            break
        data = response.json()
        page = data.get("items", []) or []
        if not page:
            break
        for item in page:
            link = str(item.get("link", "")).strip()
            title = str(item.get("title", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            if link and title:
                out.append({"url": link, "title": title, "snippet": snippet})
        start += len(page)
        if len(page) < 10:
            break
    return out


async def _search_html(client: httpx.AsyncClient, query: str) -> str:
    candidate_urls = [
        ("https://html.duckduckgo.com/html/", {"q": query}),
        ("https://lite.duckduckgo.com/lite/", {"q": query}),
        ("https://www.bing.com/search", {"q": query}),
    ]
    best_html = ""
    for url, params in candidate_urls:
        try:
            response = await client.get(
                url,
                params=params,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            html = response.text or ""
            if html and len(html) > len(best_html):
                best_html = html
            if _parse_search_results(html):
                return html
            fallback_html = await _fetch_html_with_optional_scrapling(client, f"{url}?{urlencode(params)}")
            if fallback_html and len(fallback_html) > len(best_html):
                best_html = fallback_html
            if _parse_search_results(fallback_html):
                return fallback_html
        except Exception:
            continue
    return best_html


def _parse_search_results(html: str) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    patterns = [
        re.compile(
            r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?(?:<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>)?',
            flags=re.I | re.S,
        ),
        re.compile(
            r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*result-link[^"]*"[^>]*>(.*?)</a>.*?(?:<td[^>]*class="result-snippet"[^>]*>(.*?)</td>)?',
            flags=re.I | re.S,
        ),
        re.compile(
            r'<li[^>]+class="[^"]*b_algo[^"]*"[^>]*>.*?<h2><a[^>]+href="([^"]+)"[^>]*>(.*?)</a></h2>.*?(?:<p>(.*?)</p>)?',
            flags=re.I | re.S,
        ),
    ]
    for pattern in patterns:
        for groups in pattern.findall(html):
            href = groups[0]
            title_html = groups[1] if len(groups) > 1 else ""
            snippet_html = next((group for group in groups[2:] if group), "")
            title = _html_to_text(title_html)
            snippet = _html_to_text(snippet_html or "")
            url = _resolve_search_result_url(href)
            if not url or not title:
                continue
            matches.append({"url": url, "title": title, "snippet": snippet})
        if matches:
            break
    if not matches:
        seen: set[str] = set()
        anchor_pattern = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', flags=re.I | re.S)
        for href, title_html in anchor_pattern.findall(html):
            url = _resolve_search_result_url(href)
            title = _html_to_text(title_html)
            if not url or not title:
                continue
            if url in seen:
                continue
            seen.add(url)
            matches.append({"url": url, "title": title, "snippet": ""})
    return matches


def _resolve_search_result_url(href: str) -> str | None:
    if not href:
        return None
    if href.startswith("//"):
        return f"https:{href}"
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/l/?"):
        parsed = urlparse(href)
        params = dict(parse_qsl(parsed.query))
        target = params.get("uddg")
        return target or None
    if href.startswith("/ck/a?!") or href.startswith("/search?"):
        return None
    return None


def _filter_search_matches(matches: list[dict[str, str]], mode: str) -> list[dict[str, str]]:
    filtered: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in matches:
        url = match.get("url") or ""
        title = normalize_text(match.get("title") or "")
        domain = extract_domain(url) or ""
        path = (urlparse(url).path or "").lower()
        if not domain:
            continue
        if any(blocked in domain for blocked in ["duckduckgo.com", "bing.com", "google.com", "apify.com"]):
            continue
        if mode == "ats":
            if not any(host in domain for host in ATS_HOST_MARKERS):
                continue
        else:
            if not (
                any(token in path for token in ["/careers", "/jobs", "/job", "/join", "/hiring"])
                or any(token in title for token in ["career", "job", "hiring", "startup"])
                or any(host in domain for host in ATS_HOST_MARKERS)
            ):
                continue
        if url in seen:
            continue
        seen.add(url)
        filtered.append(match)
    return filtered


def _location_query_clause(payload: dict[str, Any]) -> str:
    locations = [loc for loc in _split_locations(payload) if loc]
    if not locations:
        return payload.get("location") or ""
    if len(locations) == 1:
        return locations[0]
    return "(" + " OR ".join(f'"{loc}"' for loc in locations) + ")"


def _build_web_query(payload: dict[str, Any], strategy: dict[str, Any]) -> str:
    parts = [
        _search_query_variant(payload["query"], mode="web"),
        _location_query_clause(payload),
        payload.get("country") or "",
        "(startup OR scale-up OR founding OR venture-backed) (jobs OR careers OR hiring)",
    ]
    if strategy.get("company_stage"):
        parts.append(strategy["company_stage"])
    if strategy.get("keywords"):
        parts.append(" ".join(strategy["keywords"][:4]))
    return " ".join(part for part in parts if part).strip()


def _build_ats_query(payload: dict[str, Any], strategy: dict[str, Any]) -> str:
    parts = [
        _search_query_variant(payload["query"], mode="ats"),
        _location_query_clause(payload),
        payload.get("country") or "",
        "(site:jobs.ashbyhq.com OR site:boards.greenhouse.io OR site:job-boards.greenhouse.io OR site:jobs.lever.co OR site:jobs.smartrecruiters.com OR site:apply.workable.com)",
    ]
    if strategy.get("keywords"):
        parts.append(" ".join(strategy["keywords"][:3]))
    parts.append("(startup OR scale-up OR ai)")
    return " ".join(part for part in parts if part).strip()


def _build_startupmap_url(location: str | None, country: str | None) -> str | None:
    location_slug = _slugify_location(location)
    country_slug = _slugify_location(country)

    if location_slug and location_slug not in {"germany", "deutschland"}:
        return f"https://startupmap.one/startups/{location_slug}"
    if country_slug in {"germany", "deutschland"} or not country_slug:
        return "https://startupmap.one/startups"
    return f"https://startupmap.one/startups/{country_slug}"


def _slugify_location(value: str | None) -> str:
    if not value:
        return ""
    slug = normalize_text(value)
    slug = slug.replace("/", " ")
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug).strip("-")
    return slug


def _google_date_restrict(posted_within_hours: int | None) -> str | None:
    if posted_within_hours is None:
        return None
    if posted_within_hours <= 24:
        return "d1"
    if posted_within_hours <= 24 * 7:
        return f"d{max(1, posted_within_hours // 24)}"
    return f"w{max(1, posted_within_hours // (24 * 7))}"


def _indeed_date_posted(posted_within_hours: int | None) -> str | None:
    if posted_within_hours is None:
        return None
    if posted_within_hours <= 24:
        return "1"
    if posted_within_hours <= 24 * 3:
        return "3"
    if posted_within_hours <= 24 * 7:
        return "7"
    return "14"


def _country_code_for_indeed(country: str | None) -> str:
    if not country:
        return "de"
    normalized = normalize_text(country)
    if len(normalized) == 2:
        return normalized
    return COUNTRY_CODE_OVERRIDES.get(normalized, "de")


def _role_title_from_search_result(title: str, fallback_query: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        return fallback_query.strip() or "AI Engineer"
    separators = ["|", " - ", " — ", " at ", " · ", "::"]
    parts: list[str] = [cleaned]
    for separator in separators:
        if separator in cleaned:
            parts = [piece.strip() for piece in cleaned.split(separator) if piece.strip()]
            break
    role_keywords = (
        "engineer",
        "developer",
        "scientist",
        "researcher",
        "research",
        "specialist",
        "analyst",
        "architect",
        "intern",
        "lead",
        "manager",
        "consultant",
        "ml",
        "ai",
        "llm",
        "nlp",
        "data",
    )
    for piece in parts:
        lowered = piece.lower()
        if any(token in lowered for token in role_keywords):
            return re.sub(r"\s+", " ", piece)[:160]
    return re.sub(r"\s+", " ", parts[0])[:160]


def _infer_company_from_search_result(title: str, url: str) -> str:
    separators = ["|", "-", " at "]
    for separator in separators:
        if separator in title:
            parts = [part.strip() for part in title.split(separator) if part.strip()]
            if len(parts) >= 2:
                return parts[-1] if separator != " at " else parts[-1]
    return _company_name_from_url(url)


def _root_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    root = f"{parsed.scheme}://{parsed.netloc}"
    domain = extract_domain(root)
    if not domain:
        return None
    if any(marker in domain for marker in SHORTENER_OR_PROXY_HOSTS):
        return None
    if any(marker in domain for marker in ATS_HOST_MARKERS):
        return None
    return root


def _search_query_variant(query: str, mode: str) -> str:
    variants = [f'"{variant}"' for variant in _ai_engineer_family_variants(query)]
    joined = " OR ".join(variants[:4])
    if mode == "web":
        return f"({joined})"
    return f"({joined})"


def _theirstack_funding_stages(payload: dict[str, Any], strategy: dict[str, Any]) -> list[str]:
    stage_inputs = [
        normalize_text(str(payload.get("company_stage") or "")),
        normalize_text(str(strategy.get("company_stage") or "")),
        normalize_text(str(payload.get("strategy_prompt") or "")),
    ]
    joined = " ".join(part for part in stage_inputs if part)
    if not joined and not _looks_startup_focused(payload, strategy):
        return []

    stage_map = {
        "pre-seed": ["pre_seed"],
        "pre seed": ["pre_seed"],
        "seed": ["seed"],
        "early": ["seed", "series_a"],
        "early access": ["seed", "series_a"],
        "series a": ["series_a"],
        "series b": ["series_b"],
        "series c": ["series_c"],
        "growth": ["series_b", "series_c"],
    }

    selected: list[str] = []
    for needle, mapped in stage_map.items():
        if needle in joined:
            for value in mapped:
                if value not in selected:
                    selected.append(value)

    if selected:
        return selected
    if _looks_startup_focused(payload, strategy):
        return ["pre_seed", "seed", "series_a", "series_b"]
    return []


def _is_startup_jobs_intelligence_actor(actor_id: str | None) -> bool:
    normalized = normalize_text(actor_id or "").replace("~", "/")
    return normalized.endswith("brilliant_gum/startup-jobs-intelligence")


def _startup_jobs_intelligence_seniority(strategy: dict[str, Any]) -> str | None:
    preference = normalize_text(str(strategy.get("seniority_preference") or ""))
    mapping = {
        "junior": "entry",
        "mid": "mid",
        "senior": "senior",
        "staff_plus": "staff",
    }
    return mapping.get(preference)


def _startup_jobs_intelligence_input(
    payload: dict[str, Any],
    strategy: dict[str, Any],
    *,
    minimal: bool = False,
) -> dict[str, Any]:
    result_limit = max(1, int(payload.get("apify_limit", 0) or payload.get("result_limit", 15) or 15))
    base_query = (payload.get("query") or "AI Engineer").strip()
    search_location = payload.get("__source_location") or payload.get("location") or payload.get("country") or "Germany"
    is_remote_location = "remote" in normalize_text(str(search_location))
    actor_input: dict[str, Any] = {
        "keywords": base_query,
        "searchTerm": base_query,
        "search": base_query,
        "query": base_query,
        "location": search_location,
        "maxResults": min(result_limit * 2, 50),
        "maxItems": min(result_limit * 2, 50),
    }
    if payload.get("remote_only") or is_remote_location:
        actor_input["remoteOnly"] = True
        actor_input["remote"] = True
    if minimal:
        return actor_input

    funding_stage = _theirstack_funding_stages(payload, strategy)
    if funding_stage:
        actor_input["fundingStage"] = funding_stage
    seniority = _startup_jobs_intelligence_seniority(strategy)
    if seniority:
        actor_input["seniority"] = seniority
    if payload.get("country"):
        actor_input["country"] = payload.get("country")
    if _looks_startup_focused(payload, strategy):
        actor_input["sources"] = ["workatastartup", "greenhouse"]
    return actor_input


def _humanize_theirstack_stage(value: Any) -> str | None:
    if value is None:
        return None
    text = normalize_text(str(value))
    if not text:
        return None
    mapping = {
        "pre_seed": "Pre-Seed",
        "seed": "Seed",
        "series_a": "Series A",
        "series_b": "Series B",
        "series_c": "Series C",
        "series_d": "Series D+",
        "bootstrapped": "Bootstrapped",
        "public": "Public",
    }
    return mapping.get(text, text.replace("_", " ").title())


def _humanize_employee_count(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return text
    if not isinstance(value, (int, float)):
        return None

    count = int(value)
    if count <= 10:
        return "1 to 10"
    if count <= 50:
        return "11 to 50"
    if count <= 200:
        return "51 to 200"
    if count <= 500:
        return "201 to 500"
    if count <= 1000:
        return "501 to 1000"
    if count <= 5000:
        return "1001 to 5000"
    if count <= 10000:
        return "5001 to 10000"
    return "10,000+"


def _safe_company_website_url(url: str | None) -> str | None:
    if not url:
        return None
    if not _is_probable_company_url(url):
        return None
    return url


def _is_ats_url(url: str | None) -> bool:
    domain = extract_domain(url)
    if not domain:
        return False
    return any(marker in domain for marker in ATS_HOST_MARKERS)


async def _extract_startup_directory_entries(
    html: str,
    text: str,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    links = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    candidates: list[str] = []
    include_patterns = [pattern.lower() for pattern in source.metadata.get("company_link_patterns", []) if isinstance(pattern, str)]
    default_patterns = ["/startup", "/startups/", "/companies/", "/company/"]
    for link in links:
        lowered = link.lower()
        if lowered.startswith("#") or lowered.startswith("mailto:") or lowered.startswith("javascript:"):
            continue
        if include_patterns:
            if any(pattern in lowered for pattern in include_patterns):
                candidates.append(urljoin(source.url or "", link))
        elif any(pattern in lowered for pattern in default_patterns):
            candidates.append(urljoin(source.url or "", link))

    unique_candidates: list[str] = []
    seen = set()
    for candidate in candidates:
        cleaned = canonicalize_url(candidate)
        if cleaned in seen:
            continue
        seen.add(cleaned)
        unique_candidates.append(cleaned)

    fallback_seed = source.metadata.get("companies")
    if isinstance(fallback_seed, list):
        return [_normalize_seed_entry(seed, source, payload) for seed in fallback_seed if isinstance(seed, dict)]

    if not unique_candidates:
        # As a last resort, let AI mine the visible directory page into candidate startups.
        return await _extract_directory_candidates_via_ai(text, source, payload, strategy)

    # Directory pages can be large; use AI on the directory text plus candidate URLs to shortlist the most relevant companies.
    shortlist = await _shortlist_directory_candidates(text, unique_candidates, payload, strategy)
    output: list[dict[str, Any]] = []
    for candidate in shortlist:
        company_name = candidate.get("company_name") or _company_name_from_url(candidate["detail_url"])
        if not company_name:
            continue
        output.append(
            {
                "company_name": company_name,
                "detail_url": candidate["detail_url"],
                "summary": candidate.get("summary"),
                "city": candidate.get("city") or source.metadata.get("city"),
                "country": candidate.get("country") or source.metadata.get("country"),
                "stage": candidate.get("stage"),
                "tags": candidate.get("tags", []),
                "tags_text": " ".join(candidate.get("tags", [])),
                "ai_relevance": candidate.get("ai_relevance"),
                "target_role": payload["query"],
                "company_website_url": candidate.get("company_website_url"),
                "company_careers_url": candidate.get("company_careers_url"),
                "contacts": candidate.get("contacts", []),
                "detail_html": "",
            }
        )
    return output


def _normalize_seed_entry(seed: dict[str, Any], source: StartupHuntSourceConfig, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_name": str(seed.get("company_name", "")).strip(),
        "detail_url": str(seed.get("detail_url") or source.url or "").strip() or None,
        "summary": str(seed.get("summary", "")).strip() or None,
        "city": str(seed.get("city", "")).strip() or source.metadata.get("city"),
        "country": str(seed.get("country", "")).strip() or source.metadata.get("country"),
        "stage": str(seed.get("stage", "")).strip() or source.metadata.get("default_stage"),
        "tags": seed.get("tags", []),
        "tags_text": " ".join(seed.get("tags", [])) if isinstance(seed.get("tags"), list) else "",
        "ai_relevance": str(seed.get("ai_relevance", "")).strip() or None,
        "target_role": payload["query"],
        "company_website_url": str(seed.get("company_website_url", "")).strip() or None,
        "company_careers_url": str(seed.get("company_careers_url", "")).strip() or None,
        "contacts": seed.get("contacts", []),
        "detail_html": "",
    }


async def _shortlist_directory_candidates(
    directory_text: str,
    candidate_urls: list[str],
    payload: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    sample_urls = candidate_urls[:30]
    system = """You are extracting promising startup leads from a startup directory page for a job seeker.
Return JSON only:
{
  "companies": [
    {
      "company_name": string,
      "detail_url": string,
      "summary": string | null,
      "city": string | null,
      "country": string | null,
      "stage": string | null,
      "tags": [string],
      "ai_relevance": string | null,
      "company_website_url": string | null,
      "company_careers_url": string | null
    }
  ]
}
Choose companies that best match the target role, Germany focus, AI/ML relevance, early-stage potential, and hidden-gem signals."""
    prompt = f"""Target role: {payload['query']}
Target location: {payload['location']}, {payload.get('country') or ''}
Strategy: {json.dumps(strategy)}

Directory text excerpt:
{directory_text[:7000]}

Candidate company/detail URLs:
{json.dumps(sample_urls, indent=2)}
"""
    try:
        text = await ai_provider.generate_text(prompt, system=system, max_tokens=1800)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            companies = data.get("companies", [])
            output: list[dict[str, Any]] = []
            for company in companies:
                if not isinstance(company, dict):
                    continue
                detail_url = str(company.get("detail_url", "")).strip()
                if not detail_url:
                    continue
                output.append(
                    {
                        "company_name": str(company.get("company_name", "")).strip() or _company_name_from_url(detail_url),
                        "detail_url": detail_url,
                        "summary": str(company.get("summary", "")).strip() or None,
                        "city": str(company.get("city", "")).strip() or None,
                        "country": str(company.get("country", "")).strip() or None,
                        "stage": str(company.get("stage", "")).strip() or None,
                        "tags": [str(tag).strip() for tag in company.get("tags", []) if str(tag).strip()],
                        "ai_relevance": str(company.get("ai_relevance", "")).strip() or None,
                        "company_website_url": str(company.get("company_website_url", "")).strip() or None,
                        "company_careers_url": str(company.get("company_careers_url", "")).strip() or None,
                        "contacts": [],
                    }
                )
            if output:
                return output[:12]
    except Exception:
        pass

    fallback: list[dict[str, Any]] = []
    for url in sample_urls[:12]:
        fallback.append(
            {
                "company_name": _company_name_from_url(url),
                "detail_url": url,
                "summary": None,
                "city": None,
                "country": None,
                "stage": None,
                "tags": [],
                "ai_relevance": None,
                "company_website_url": None,
                "company_careers_url": None,
                "contacts": [],
            }
        )
    return fallback


async def _extract_directory_candidates_via_ai(
    directory_text: str,
    source: StartupHuntSourceConfig,
    payload: dict[str, Any],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    system = """Extract promising startup company leads from a startup directory page.
Return JSON only:
{
  "companies": [
    {
      "company_name": string,
      "summary": string | null,
      "city": string | null,
      "country": string | null,
      "stage": string | null,
      "tags": [string],
      "ai_relevance": string | null
    }
  ]
}"""
    prompt = f"""Target role: {payload['query']}
Target location: {payload['location']}, {payload.get('country') or ''}
Strategy: {json.dumps(strategy)}

Directory text:
{directory_text[:7000]}
"""
    try:
        text = await ai_provider.generate_text(prompt, system=system, max_tokens=1200)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            companies = data.get("companies", [])
            output: list[dict[str, Any]] = []
            for company in companies:
                if not isinstance(company, dict):
                    continue
                name = str(company.get("company_name", "")).strip()
                if not name:
                    continue
                output.append(
                    {
                        "company_name": name,
                        "detail_url": source.url,
                        "summary": str(company.get("summary", "")).strip() or None,
                        "city": str(company.get("city", "")).strip() or source.metadata.get("city"),
                        "country": str(company.get("country", "")).strip() or source.metadata.get("country"),
                        "stage": str(company.get("stage", "")).strip() or None,
                        "tags": [str(tag).strip() for tag in company.get("tags", []) if str(tag).strip()],
                        "tags_text": " ".join([str(tag).strip() for tag in company.get("tags", []) if str(tag).strip()]),
                        "ai_relevance": str(company.get("ai_relevance", "")).strip() or None,
                        "target_role": payload["query"],
                        "company_website_url": None,
                        "company_careers_url": None,
                        "contacts": [],
                        "detail_html": "",
                    }
                )
            return output[:10]
    except Exception:
        pass
    return []


async def _infer_company_metadata(page_text: str, company_name: str, target_role: str) -> dict[str, Any]:
    if not page_text:
        return {}
    system = """Extract lightweight startup metadata from a company page.
Return JSON only:
{
  "stage": string | null,
  "company_size": string | null,
  "city": string | null,
  "country": string | null,
  "english_friendly": boolean | null,
  "ai_relevance": string | null,
  "relocation_support": string | null
}"""
    prompt = f"""Company: {company_name}
Target role: {target_role}
Company page text:
{page_text[:5000]}
"""
    try:
        text = await ai_provider.generate_text(prompt, system=system, max_tokens=500)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            return {
                "stage": str(data.get("stage", "")).strip() or None,
                "company_size": str(data.get("company_size", "")).strip() or None,
                "city": str(data.get("city", "")).strip() or None,
                "country": str(data.get("country", "")).strip() or None,
                "english_friendly": bool(data.get("english_friendly")) if data.get("english_friendly") is not None else None,
                "ai_relevance": str(data.get("ai_relevance", "")).strip() or None,
                "relocation_support": str(data.get("relocation_support", "")).strip() or None,
            }
    except Exception:
        pass
    return {}


def _company_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/").split("/")[-1]
    if not path:
        return extract_domain(url) or "Startup lead"
    cleaned = re.sub(r"[-_]+", " ", path)
    cleaned = re.sub(r"\b(startup|startups|company|companies)\b", "", cleaned, flags=re.I).strip()
    return cleaned.title() or (extract_domain(url) or "Startup lead")


def _base_company_payload(source: StartupHuntSourceConfig) -> dict[str, Any]:
    metadata = source.metadata or {}
    return {
        "stage": metadata.get("stage"),
        "company_size": metadata.get("company_size"),
        "country": metadata.get("country"),
        "city": metadata.get("city"),
        "english_friendly": bool(metadata.get("english_friendly")),
        "ai_relevance": metadata.get("ai_relevance") or metadata.get("industry"),
        "relocation_support": metadata.get("relocation_support"),
        "company_website_url": metadata.get("company_website_url") or source.url,
        "company_careers_url": metadata.get("careers_url"),
        "source_tags": metadata.get("tags", []),
    }


def _contacts_from_metadata(metadata: dict[str, Any], company_name: str) -> list[dict[str, Any]]:
    contacts: list[dict[str, Any]] = []
    for item in metadata.get("contacts", []) if isinstance(metadata.get("contacts"), list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        title = str(item.get("title", "")).strip()
        email = str(item.get("email", "")).strip() or None
        if not name and not title and not email:
            continue
        contacts.append(
            {
                "name": name or company_name,
                "title": title or "Contact",
                "contact_type": _infer_contact_type(title),
                "email": email,
                "email_confidence": "high" if email else "unknown",
                "linkedin_url": str(item.get("linkedin_url", "")).strip() or None,
                "source": "metadata",
                "provider_chain": ["metadata"],
            }
        )
    return contacts


def _contacts_from_page(html: str, page_url: str) -> list[dict[str, Any]]:
    text = _html_to_text(html)
    emails = sorted(set(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", html, flags=re.I)))
    linkedin_urls = sorted(set(re.findall(r"https?://(?:www\.)?linkedin\.com/[^\s\"'<>]+", html, flags=re.I)))
    title_hits = re.findall(r"\b(founder|co-founder|ceo|cto|head of ai|head of machine learning|hiring manager|talent partner|recruiter)\b", text, flags=re.I)
    contacts: list[dict[str, Any]] = []
    for email in emails[:6]:
        local_part = email.split("@", 1)[0].replace(".", " ").replace("_", " ")
        contacts.append(
            {
                "name": local_part.title(),
                "title": "Email Contact",
                "contact_type": "recruiter",
                "email": email,
                "email_confidence": "medium",
                "linkedin_url": None,
                "source": page_url,
                "provider_chain": ["page_extract"],
            }
        )
    for linkedin_url in linkedin_urls[:8]:
        slug = linkedin_url.rstrip("/").split("/")[-1]
        title_hint = next((match for match in title_hits if any(token in slug.lower() for token in match.lower().split())), "LinkedIn Contact")
        contacts.append(
            {
                "name": slug.replace("-", " ").title(),
                "title": title_hint.title() if title_hint != "LinkedIn Contact" else "LinkedIn Contact",
                "contact_type": _infer_contact_type(f"{slug} {title_hint}"),
                "email": None,
                "email_confidence": "unknown",
                "linkedin_url": linkedin_url,
                "source": page_url,
                "provider_chain": ["page_extract"],
            }
        )
    if title_hits and not contacts:
        primary = title_hits[0]
        contacts.append(
            {
                "name": primary.title(),
                "title": primary.title(),
                "contact_type": _infer_contact_type(primary),
                "email": None,
                "email_confidence": "unknown",
                "linkedin_url": None,
                "source": page_url,
                "provider_chain": ["page_extract"],
            }
        )
    return contacts


def _html_to_text(html: str) -> str:
    cleaned = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    cleaned = re.sub(r"<style\b[^>]*>.*?</style>", " ", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_careers_url(html: str, page_url: str) -> str | None:
    links = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    for link in links:
        lowered = link.lower()
        if any(token in lowered for token in ["/careers", "/jobs", "/job", "greenhouse.io", "lever.co", "join.com", "workable.com", "smartrecruiters.com", "myworkdayjobs.com", "kenjo.io", "teamtailor.com", "personio"]):
            if lowered.startswith("http"):
                return link
            return urljoin(page_url, link)
    return None


def _extract_matching_job_url(html: str, page_url: str, target_role: str) -> str | None:
    link_matches = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, flags=re.I | re.S)
    if not link_matches:
        return None

    query_tokens = set(tokenize(target_role))
    best_url: str | None = None
    best_score = 0
    for href, label_html in link_matches:
        label = _html_to_text(label_html)
        if not label:
            continue
        absolute_url = href if href.startswith("http") else urljoin(page_url, href)
        lowered_url = absolute_url.lower()
        if not any(token in lowered_url for token in ["/jobs", "/job", "/careers", "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "smartrecruiters.com", "myworkdayjobs.com", "personio", "teamtailor", "kenjo.io"]):
            continue
        label_tokens = set(tokenize(label))
        score = len(query_tokens & label_tokens)
        if "senior" in label.lower() and "senior" not in target_role.lower():
            score -= 1
        if score > best_score:
            best_score = score
            best_url = absolute_url
    return best_url if best_score > 0 else None


def _extract_company_website_url(html: str, page_url: str) -> str | None:
    links = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    page_domain = extract_domain(page_url)
    for link in links:
        lowered = link.lower()
        if lowered.startswith("mailto:") or lowered.startswith("javascript:") or "linkedin.com" in lowered:
            continue
        absolute = link if lowered.startswith("http") else urljoin(page_url, link)
        domain = extract_domain(absolute)
        if not domain or domain == page_domain:
            continue
        if not _is_probable_company_url(absolute, page_url):
            continue
        return absolute
    return None


def _normalize_apify_actor_id(actor_id: str) -> str:
    normalized = actor_id.strip().strip("/")
    if "/" in normalized and "~" not in normalized:
        owner, name = normalized.split("/", 1)
        if owner and name:
            return f"{owner}~{name}"
    return normalized


def _is_probable_company_url(url: str | None, page_url: str | None = None) -> bool:
    domain = extract_domain(url)
    if not domain:
        return False
    page_domain = extract_domain(page_url) if page_url else None
    if page_domain and domain == page_domain:
        return False
    if any(marker in domain for marker in INFRASTRUCTURE_HOST_MARKERS):
        return False
    if any(marker in domain for marker in [*SHORTENER_OR_PROXY_HOSTS, "startupmap.one", "facebook.com", "instagram.com", "x.com", "twitter.com", "linkedin.com"]):
        return False
    return True


def _infer_contact_type(value: str) -> str:
    lowered = value.lower()
    if "founder" in lowered or "cofounder" in lowered or "co-founder" in lowered:
        return "founder"
    if "chief executive" in lowered or re.search(r"\bceo\b", lowered):
        return "ceo"
    if "hiring" in lowered or "talent" in lowered or "recruit" in lowered:
        return "recruiter"
    if "head of ai" in lowered or "ml" in lowered or "machine learning" in lowered or "ai" in lowered:
        return "ai_lead"
    return "hiring_manager"


def _merge_contacts(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str | None, str | None, str | None]] = set()
    merged: list[dict[str, Any]] = []
    for item in primary + secondary:
        key = (item.get("email"), item.get("linkedin_url"), item.get("name"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged[:10]


async def _enrich_opportunities_contacts(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    provider = settings.startup_hunt_contact_enrichment_provider.strip().lower()
    if provider not in {"apollo", "pdl"}:
        if settings.people_data_labs_api_key:
            provider = "pdl"
        elif settings.apollo_api_key:
            provider = "apollo"
        else:
            return opportunities
    if provider == "apollo" and not settings.apollo_api_key:
        return opportunities
    if provider == "pdl" and not settings.people_data_labs_api_key:
        return opportunities

    async with httpx.AsyncClient(timeout=settings.startup_hunt_timeout_seconds) as client:
        for opportunity in opportunities:
            contacts = opportunity.get("contacts", [])
            if not contacts:
                continue
            enriched: list[dict[str, Any]] = []
            for contact in contacts[:4]:
                if contact.get("email"):
                    enriched.append(contact)
                    continue
                enriched_contact = await _enrich_contact(client, provider, contact, opportunity)
                enriched.append(enriched_contact or contact)
            opportunity["contacts"] = _merge_contacts(enriched, contacts[4:])
    return opportunities


async def _enrich_contact(
    client: httpx.AsyncClient,
    provider: str,
    contact: dict[str, Any],
    opportunity: dict[str, Any],
) -> dict[str, Any] | None:
    if provider == "apollo":
        return await _enrich_contact_apollo(client, contact, opportunity)
    if provider == "pdl":
        return await _enrich_contact_pdl(client, contact, opportunity)
    return None


async def _enrich_contact_apollo(
    client: httpx.AsyncClient,
    contact: dict[str, Any],
    opportunity: dict[str, Any],
) -> dict[str, Any] | None:
    name = str(contact.get("name", "")).strip()
    if not name:
        return None
    response = await client.post(
        "https://api.apollo.io/api/v1/people/match",
        headers={"X-Api-Key": settings.apollo_api_key},
        params={
            "name": name,
            "organization_name": opportunity.get("company_name"),
            "domain": opportunity.get("company_domain"),
            "linkedin_url": contact.get("linkedin_url"),
        },
    )
    if response.status_code >= 400:
        return None
    data = response.json()
    person = data.get("person") or data.get("contact") or data
    email = person.get("email") or person.get("work_email")
    linkedin_url = person.get("linkedin_url") or contact.get("linkedin_url")
    title = person.get("title") or contact.get("title")
    if not email and not linkedin_url and not title:
        return None
    return {
        **contact,
        "title": title or contact.get("title"),
        "email": email or contact.get("email"),
        "email_confidence": "high" if email else contact.get("email_confidence", "unknown"),
        "linkedin_url": linkedin_url,
        "source": "apollo",
        "provider_chain": [*(contact.get("provider_chain") or []), "apollo"],
    }


async def _enrich_contact_pdl(
    client: httpx.AsyncClient,
    contact: dict[str, Any],
    opportunity: dict[str, Any],
) -> dict[str, Any] | None:
    name = str(contact.get("name", "")).strip()
    if not name:
        return None
    response = await client.post(
        "https://api.peopledatalabs.com/v5/person/enrich",
        headers={"X-Api-Key": settings.people_data_labs_api_key, "Content-Type": "application/json"},
        json={
            "name": name,
            "company": opportunity.get("company_name"),
            "website": opportunity.get("company_domain"),
            "linkedin_url": contact.get("linkedin_url"),
        },
    )
    if response.status_code >= 400:
        return None
    data = response.json().get("data") or response.json()
    work_email = data.get("work_email")
    linkedin_url = data.get("linkedin_url") or contact.get("linkedin_url")
    title = data.get("job_title") or contact.get("title")
    if not work_email and not linkedin_url and not title:
        return None
    return {
        **contact,
        "title": title or contact.get("title"),
        "email": work_email or contact.get("email"),
        "email_confidence": "high" if work_email else contact.get("email_confidence", "unknown"),
        "linkedin_url": linkedin_url,
        "source": "pdl",
        "provider_chain": [*(contact.get("provider_chain") or []), "pdl"],
    }


def _score_opportunity(
    item: dict[str, Any],
    payload: dict[str, Any],
    strategy: dict[str, Any],
    existing_opportunities: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    query_tokens = tokenize(payload["query"])
    normalized_title = normalize_text(item["role_title"])
    location_target = normalize_text(payload["location"])
    country_target = normalize_text(payload.get("country") or "")
    raw_text = normalize_text(item.get("raw_text", ""))
    company_payload = item.get("company_payload") or {}
    location_text = normalize_text(item["location"])
    company_stage = normalize_text(str(company_payload.get("stage", "") or ""))
    company_size = normalize_text(str(company_payload.get("company_size", "") or ""))
    ai_relevance = normalize_text(str(company_payload.get("ai_relevance", "") or ""))
    direct_url = item.get("direct_apply_url")
    contacts = item.get("contacts", [])
    posted_at: datetime | None = item.get("posted_at")
    source_bucket = _result_source_bucket(item)
    seniority_preference = (
        _normalize_seniority_preference(strategy.get("seniority_preference"))
        or _infer_seniority_preference_from_prompt(payload.get("strategy_prompt"))
    )
    strict_mid_preference = _strict_mid_level_preference(payload.get("strategy_prompt"), seniority_preference)
    role_seniority = _role_seniority_level(item["role_title"], raw_text)
    stack_signals = _query_stack_signals(payload["query"])

    is_outreach_lead = item.get("opportunity_kind") == "outreach_lead"

    if query_tokens and not any(token in raw_text or token in normalized_title for token in query_tokens):
        if not (is_outreach_lead and ai_relevance):
            return None, "Missing query keyword match"

    if not is_outreach_lead and not _role_title_matches_query(payload["query"], item["role_title"], raw_text):
        return None, "Role title did not match requested role family"

    if strict_mid_preference and role_seniority in {"senior", "staff_plus"}:
        return None, "Role seniority exceeded the requested mid-level range"

    max_years = _max_years_allowed(payload.get("strategy_prompt"), seniority_preference)
    if max_years is not None and not is_outreach_lead:
        min_years_required = _extract_min_years_required(item.get("raw_text", "") or "")
        if min_years_required is not None and min_years_required > max_years:
            return None, f"Role requires {min_years_required}+ years experience (limit {max_years})"

    if payload.get("direct_links_only") and not direct_url:
        return None, "Direct links only filter removed this result"

    if payload.get("english_friendly_only") and not bool(company_payload.get("english_friendly")):
        languages = [normalize_text(str(v)) for v in company_payload.get("source_tags", [])]
        if "english" not in languages:
            return None, "English-friendly filter removed this result"

    if payload.get("company_stage") and payload["company_stage"].strip().lower() not in company_stage:
        return None, "Company stage filter removed this result"

    is_remote = "remote" in location_text or "anywhere" in location_text or "distributed" in location_text
    location_targets = [normalize_text(loc) for loc in _split_locations(payload)] or [location_target]
    matched_any_location = False
    for target in location_targets:
        if not target:
            continue
        if target == "remote" or target == "anywhere":
            if is_remote:
                matched_any_location = True
                break
            continue
        if _location_matches(target, country_target, location_text, company_payload, is_remote):
            matched_any_location = True
            break
    if not matched_any_location:
        return None, "Location filter removed this result"

    if payload.get("remote_only") and not is_remote:
        return None, "Remote-only filter removed this result"

    age_hours = 999999.0
    if posted_at:
        age_hours = max(0.0, (now_utc() - posted_at).total_seconds() / 3600)
        cutoff = payload.get("posted_within_hours")
        if cutoff is not None and age_hours > cutoff:
            return None, "Freshness filter removed this result"

    score = 0.0
    labels: list[str] = []
    reasons: list[str] = []

    token_hits = [token for token in query_tokens if token in raw_text or token in normalized_title]
    score += len(token_hits) * 4
    if token_hits:
        reasons.append(f"Matched role keywords: {', '.join(sorted(set(token_hits)))}")

    city_hits = [city for city in strategy.get("preferred_cities", []) if city and city in location_text]
    if city_hits or "germany" in location_target or "berlin" in location_target or "munich" in location_target:
        score += 2
        labels.append("Germany Match")
        if city_hits:
            reasons.append(f"Matched preferred city: {', '.join(city_hits)}")

    if posted_at:
        freshness = max(0.0, 72 - min(age_hours, 72))
        score += freshness / 6
        if age_hours <= 24:
            labels.append("Fresh")
            reasons.append(f"Posted about {int(age_hours)} hours ago")

    if direct_url:
        score += 3
        labels.append("Direct Apply")
        reasons.append("Direct company or ATS apply link available")

    if item["opportunity_kind"] == "outreach_lead":
        score += 1.5

    if seniority_preference == "mid":
        if role_seniority == "mid":
            score += 2
            reasons.append("Role seniority aligns with mid-level preference")
        elif role_seniority == "junior":
            score -= 1.5
        elif role_seniority == "senior":
            score -= 7
            reasons.append("Senior title penalized for mid-level preference")
        elif role_seniority == "staff_plus":
            score -= 10
            reasons.append("Staff/principal title heavily penalized for mid-level preference")
    elif seniority_preference == "junior":
        if role_seniority == "junior":
            score += 2.5
            reasons.append("Role seniority aligns with junior preference")
        elif role_seniority in {"senior", "staff_plus"}:
            score -= 5
    elif seniority_preference == "senior":
        if role_seniority in {"senior", "staff_plus"}:
            score += 2
            reasons.append("Role seniority aligns with senior preference")

    if _looks_startup_focused(payload, strategy):
        if _is_startup_sized(company_size):
            score += 2
            labels.append("Hidden Gem")
            reasons.append(f"Startup-sized team signal: {company_payload.get('company_size')}")
        elif _is_large_company(company_size):
            if any(term in company_size for term in ["10000", "10,000", "5001", "enterprise"]):
                score -= 8
                reasons.append("Large enterprise team size penalized for startup-focused hunt")
            elif any(term in company_size for term in ["1001", "large"]):
                score -= 5
                reasons.append("Larger-company team size penalized for startup-focused hunt")
            else:
                score -= 3

    if company_stage:
        desired_stage = strategy.get("company_stage") or normalize_text(payload.get("company_stage") or "")
        if desired_stage and desired_stage in company_stage:
            score += 2
            reasons.append(f"Startup stage matches preference: {company_payload.get('stage')}")
        if company_stage in {"pre-seed", "seed", "series a"}:
            score += 1.5
            labels.append("Hidden Gem")

    if ai_relevance:
        if any(token in ai_relevance for token in ["ai", "ml", "machine learning", "llm", "data", "model"]):
            score += 2
            labels.append("AI/ML Fit")
            reasons.append(f"Company signal: {company_payload.get('ai_relevance')}")
        stack_hits = [signal for signal in stack_signals if signal in ai_relevance or signal in raw_text or signal in normalized_title]
        if stack_hits:
            score += min(len(stack_hits), 2) * 0.75
            reasons.append(f"Modern AI stack signal: {', '.join(sorted(set(stack_hits)))}")

    if bool(company_payload.get("english_friendly")):
        score += 1
        reasons.append("English-friendly company signal present")

    founder_like = any(contact.get("contact_type") in {"founder", "ceo", "ai_lead", "hiring_manager"} for contact in contacts)
    if founder_like:
        score += 2
        labels.append("Outreach Friendly")
        reasons.append("Founder or senior hiring contact found")
    elif contacts:
        score += 1

    if source_bucket == "ats":
        score += 1.5
    elif source_bucket in {"web", "indeed", "apify"}:
        score += 0.75
    elif source_bucket == "startupmap":
        score += 0.25
    elif source_bucket == "crawler":
        score += 0.5

    if _looks_startup_focused(payload, strategy):
        if source_bucket == "startupmap":
            score += 1.25
            reasons.append("Startup directory source boosted for hidden-gem discovery")
        elif source_bucket == "web":
            score += 1.0
            reasons.append("Web-discovered startup lead boosted for hidden-gem discovery")
        elif source_bucket == "crawler":
            score += 0.75

    if strategy.get("hidden_gem_signals"):
        score += min(len(strategy["hidden_gem_signals"]), 2)

    canonical_key = item.get("canonical_job_url") or f'{normalize_text(item["company_name"])}|{normalize_text(item["role_title"])}|{normalize_text(item["location"])}'
    existing = existing_opportunities.get(canonical_key)

    citation = item["citation"]
    citation["evidence"] = (citation.get("evidence") or []) + reasons[:3]

    return ({
        "company_name": item["company_name"],
        "company_domain": item["company_domain"],
        "company_website_url": item.get("company_website_url"),
        "company_careers_url": item.get("company_careers_url"),
        "role_title": item["role_title"],
        "location": item["location"],
        "country": item.get("country"),
        "source_name": item["source_name"],
        "source_type": item["source_type"],
        "direct_apply_url": direct_url,
        "canonical_job_url": item.get("canonical_job_url"),
        "portal_job_url": item.get("portal_job_url"),
        "posted_at": posted_at.isoformat() if posted_at else None,
        "opportunity_kind": item["opportunity_kind"],
        "score_total": round(score, 3),
        "score_labels": sorted(set(labels)),
        "score_reasons": reasons[:5],
        "citation": citation,
        "company": company_payload,
        "contacts": contacts,
        "saved": bool(existing),
        "saved_status": existing.get("opportunity_status") if existing else None,
        "saved_opportunity_id": existing.get("id") if existing else None,
        "rank_age_hours": age_hours,
        "source_bucket": source_bucket,
        "cache_hit": bool(item.get("cache_hit")),
        "description_text": item.get("description_text"),
    }, None)


def _dedupe_opportunities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    key_to_group: dict[str, int] = {}
    for item in items:
        keys = _dedupe_keys(item)
        matched_indexes = [key_to_group[key] for key in keys if key in key_to_group]
        if not matched_indexes:
            groups.append(item)
            group_index = len(groups) - 1
        else:
            group_index = matched_indexes[0]
            merged = groups[group_index]
            for other_index in sorted(set(matched_indexes[1:]), reverse=True):
                merged = _merge_duplicate_opportunities(_prefer_opportunity(merged, groups[other_index]), groups[other_index] if _prefer_opportunity(merged, groups[other_index]) is merged else merged)
                groups[other_index] = merged
            preferred = _prefer_opportunity(groups[group_index], item)
            other = item if preferred is groups[group_index] else groups[group_index]
            groups[group_index] = _merge_duplicate_opportunities(preferred, other)
        for key in keys:
            key_to_group[key] = group_index
    seen_groups: set[int] = set()
    output: list[dict[str, Any]] = []
    for index, item in enumerate(groups):
        canonical_index = index
        for key in _dedupe_keys(item):
            canonical_index = min(canonical_index, key_to_group.get(key, index))
        if canonical_index in seen_groups:
            continue
        seen_groups.add(canonical_index)
        output.append(_finalize_merged_opportunity(groups[canonical_index]))
    return output


def _looks_startup_focused(payload: dict[str, Any], strategy: dict[str, Any]) -> bool:
    prompt = normalize_text(payload.get("strategy_prompt") or "")
    if payload.get("company_stage"):
        return True
    if strategy.get("hidden_gem_signals"):
        return True
    return any(term in prompt for term in ["startup", "start-up", "hidden gem", "founder-led", "early access", "seed", "pre-seed"])


def _is_startup_sized(company_size: str) -> bool:
    if not company_size:
        return False
    return any(term in company_size for term in ["1 to 10", "11 to 50", "51 to 200", "201 to 500", "1-10", "11-50", "51-200", "201-500", "100-500", "under 500"])


def _is_large_company(company_size: str) -> bool:
    if not company_size:
        return False
    return any(term in company_size for term in ["1001", "5001", "10,000", "10000", "5000+", "10000+", "2,900+", "2900+", "10,000+", "1001 to 5000", "large", "enterprise"])


def _normalize_seniority_preference(value: str | None) -> str | None:
    text = normalize_text(value or "")
    if not text:
        return None
    if text in {"junior", "entry", "entry level", "entry-level", "graduate", "new grad", "intern", "internship"}:
        return "junior"
    if text in {
        "mid",
        "mid-level",
        "mid level",
        "midlevel",
        "intermediate",
        "ic",
        "ic role",
        "individual contributor",
        "3+ years",
        "3 years",
        "2-5 years",
        "3-5 years",
        "not senior",
    }:
        return "mid"
    if text in {"senior", "sr", "sr.", "lead", "lead role", "lead-level", "lead level"}:
        return "senior"
    if text in {"staff", "staff+", "staff_plus", "principal", "head", "director"}:
        return "staff_plus"
    if "junior" in text or "intern" in text or "entry" in text or "graduate" in text:
        return "junior"
    if "mid" in text or "intermediate" in text or "3+" in text or "ic" in text:
        return "mid"
    if "staff" in text or "principal" in text or "head" in text:
        return "staff_plus"
    if "senior" in text or " sr" in text or "lead" in text:
        return "senior"
    return None


def _infer_seniority_preference_from_prompt(prompt: str | None) -> str | None:
    text = normalize_text(prompt or "")
    if not text:
        return None
    if any(term in text for term in ["entry level", "entry-level", "junior", "new grad", "graduate", "0-2 years", "1-2 years"]):
        return "junior"
    if any(term in text for term in ["3+ years", "3 years", "mid-level", "mid level", "not senior", "ic role", "individual contributor", "2-5 years", "3-5 years"]):
        return "mid"
    if any(term in text for term in ["senior", "staff", "principal", "lead role", "lead-level", "lead level"]):
        return "senior"
    return None


def _strict_mid_level_preference(prompt: str | None, seniority_preference: str | None) -> bool:
    text = normalize_text(prompt or "")
    if seniority_preference != "mid":
        return False
    return any(
        term in text
        for term in [
            "mid-level",
            "mid level",
            "3+ years",
            "3 years",
            "2-5 years",
            "3-5 years",
            "not senior",
            "not staff",
            "not principal",
            "individual contributor",
            "ic role",
        ]
    )


_EXPERIENCE_YEAR_PATTERNS = [
    re.compile(r"(\d{1,2})\s*(?:\+|plus)\s*(?:years?|yrs?|jahre|jahren|ans|años|anni)", re.IGNORECASE),
    re.compile(r"(?:minimum|at\s+least|min\.?|mindestens|au\s+moins|at\s+a\s+minimum\s+of)\s+(\d{1,2})\s*(?:years?|yrs?|jahre|jahren|ans)", re.IGNORECASE),
    re.compile(r"(\d{1,2})\s*[-–]\s*\d{1,2}\s*(?:years?|yrs?|jahre|jahren|ans)", re.IGNORECASE),
    re.compile(r"(\d{1,2})\s*(?:years?|yrs?|jahre|jahren|ans)\s+(?:of\s+)?(?:experience|exp|berufserfahrung|expérience|experiencia|esperienza)", re.IGNORECASE),
]


def _extract_min_years_required(raw_text: str) -> int | None:
    if not raw_text:
        return None
    candidates: list[int] = []
    for pattern in _EXPERIENCE_YEAR_PATTERNS:
        for match in pattern.finditer(raw_text):
            try:
                value = int(match.group(1))
            except (ValueError, IndexError):
                continue
            if 0 < value <= 25:
                candidates.append(value)
    if not candidates:
        return None
    return min(candidates)


def _max_years_allowed(prompt: str | None, seniority_preference: str | None) -> int | None:
    text = normalize_text(prompt or "")
    if seniority_preference == "junior":
        return 2
    if seniority_preference == "mid":
        if "3+ years" in text or "3 years" in text or "2-4 years" in text or "2-3 years" in text:
            return 4
        if "4+ years" in text or "4 years" in text or "3-5 years" in text:
            return 5
        if "5+ years" in text or "5 years" in text:
            return 6
        return 5
    if seniority_preference == "senior":
        return None
    return None


def _role_seniority_level(role_title: str, raw_text: str) -> str:
    title_text = normalize_text(role_title)
    body_text = normalize_text(raw_text)
    combined = f"{title_text} {body_text}"
    if any(term in combined for term in ["principal", "staff", "head of", "director", "vp ", "vice president"]):
        return "staff_plus"
    if any(term in combined for term in [" senior", "senior ", "sr ", "sr.", "lead "]):
        return "senior"
    if any(term in combined for term in ["junior", "entry level", "entry-level", "graduate", "intern", "werkstudent", "practicum", "praktikum", "praktikant"]):
        return "junior"
    return "mid"


def _query_specialty_terms(query: str) -> list[str]:
    query_text = _normalize_role_query_aliases(query)
    specialties: list[str] = []
    if any(term in query_text for term in ["applied ai", "ai engineer", "artificial intelligence"]):
        specialties.append("ai")
    if any(term in query_text for term in ["machine learning", "ml engineer"]):
        specialties.append("ml")
    if "nlp" in query_text or "natural language" in query_text:
        specialties.append("nlp")
    if "llm" in query_text:
        specialties.append("llm")
    return specialties


def _query_stack_signals(query: str) -> list[str]:
    query_text = _normalize_role_query_aliases(query)
    signals: list[str] = []
    if "rag" in query_text:
        signals.append("rag")
    if "agent" in query_text:
        signals.append("agent")
    if "mlops" in query_text:
        signals.append("mlops")
    if "fastapi" in query_text:
        signals.append("fastapi")
    return signals


def _matches_ai_specialty_query(query: str, role_title: str, raw_text: str) -> bool:
    query_text = _normalize_role_query_aliases(query)
    title_text = normalize_text(role_title)
    body_text = normalize_text(raw_text)
    specialties = _query_specialty_terms(query)
    if not specialties:
        return True

    if "ai engineer" in query_text or "ml engineer" in query_text or "machine learning engineer" in query_text:
        engineer_aliases = [
            "ai engineer",
            "applied ai engineer",
            "ml engineer",
            "machine learning engineer",
            "llm engineer",
            "mlops engineer",
            "nlp engineer",
            "ai platform engineer",
            "research engineer",
            "applied research engineer",
            "ml research engineer",
        ]
        if any(alias in title_text for alias in engineer_aliases):
            return True

    title_hits = 0
    body_hits = 0
    title_aliases = {
        "ai": ["ai", "applied ai", "artificial intelligence", "machine learning", "ml", "llm"],
        "ml": ["machine learning", "ml", "mlops", "applied ai"],
        "nlp": ["nlp", "natural language", "language model", "llm"],
        "llm": ["llm", "language model", "generative ai"],
        "rag": ["rag", "retrieval augmented", "retrieval-augmented"],
        "agent": ["agent", "agentic"],
        "mlops": ["mlops", "machine learning platform", "model platform", "ai platform"],
    }
    for specialty in specialties:
        aliases = title_aliases.get(specialty, [specialty])
        if any(alias in title_text for alias in aliases):
            title_hits += 1
        elif any(alias in body_text for alias in aliases):
            body_hits += 1

    if title_hits >= 1:
        return True
    if "engineer" in query_text and body_hits >= max(2, len(specialties)):
        return True
    return False


def _role_title_matches_query(query: str, role_title: str, raw_text: str) -> bool:
    query_text = _normalize_role_query_aliases(query)
    title_text = normalize_text(role_title)
    body_text = normalize_text(raw_text)

    ai_family_titles = (
        "ai engineer",
        "applied ai engineer",
        "ml engineer",
        "machine learning engineer",
        "llm engineer",
        "mlops engineer",
        "nlp engineer",
        "ai platform engineer",
        "research engineer",
        "applied research engineer",
        "ml research engineer",
        "ai researcher",
        "ml researcher",
        "ai scientist",
        "ml scientist",
        "applied scientist",
        "machine learning scientist",
        "data scientist",
        "ai specialist",
        "ml specialist",
        "nlp specialist",
        "llm specialist",
        "ai architect",
        "ml architect",
        "ai intern",
        "ml intern",
        "machine learning intern",
        "ai developer",
        "ml developer",
        "generative ai",
        "gen ai",
        "computer vision",
        "deep learning",
        "rag engineer",
        "ai/ml",
    )

    if any(term in query_text for term in ["ai engineer", "ml engineer", "machine learning engineer", "ai ", " ai", "ml ", " ml", "llm", "nlp", "machine learning", "applied ai", "mlops", "rag"]):
        if any(term in title_text for term in ai_family_titles):
            return True

    ai_signal_tokens = ("ai", "ml", "machine learning", "applied ai", "llm", "nlp", "mlops", "generative", "deep learning", "rag", "agent")
    if "ai" in query_text or "ml" in query_text or "machine learning" in query_text or "llm" in query_text or "nlp" in query_text:
        title_signal = any(token in title_text for token in ai_signal_tokens)
        body_signal = any(token in body_text for token in ai_signal_tokens)
        if not (title_signal or body_signal):
            return False
        role_function_tokens = (
            "engineer",
            "developer",
            "architect",
            "scientist",
            "researcher",
            "research",
            "specialist",
            "intern",
            "lead",
            "analyst",
            "consultant",
            "manager",
            "ml",
            "ai",
        )
        if not any(token in title_text for token in role_function_tokens):
            return False
        return True

    required_groups: list[tuple[str, ...]] = []
    if "engineer" in query_text:
        required_groups.append(("engineer", "developer", "architect"))
    if "scientist" in query_text:
        required_groups.append(("scientist",))
    if "manager" in query_text:
        required_groups.append(("manager", "lead"))
    if "research" in query_text:
        required_groups.append(("research", "researcher"))

    for group in required_groups:
        if not any(token in title_text for token in group):
            return False

    return True


def _dedupe_keys(item: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    canonical = item.get("canonical_job_url")
    if canonical:
        keys.append(f"url:{canonical}")

    direct_url = item.get("direct_apply_url")
    if direct_url:
        keys.append(f"url:{canonicalize_url(direct_url)}")

    portal_url = item.get("portal_job_url")
    if portal_url:
        keys.append(f"url:{canonicalize_url(portal_url)}")

    role_key = _normalize_role_for_dedupe(item.get("role_title", ""))
    company_key = normalize_text(item.get("company_name", ""))
    location_key = _normalize_location_for_dedupe(item.get("location", ""), item.get("country"))
    domain_key = normalize_text(item.get("company_domain") or extract_domain(item.get("company_website_url")) or "")

    if company_key and role_key:
        keys.append(f"semantic:{company_key}|{role_key}|{location_key}")
    if domain_key and role_key:
        keys.append(f"semantic-domain:{domain_key}|{role_key}|{location_key}")
    return keys


def _normalize_role_for_dedupe(value: str) -> str:
    tokens = [
        token
        for token in tokenize(value)
        if token
        not in {
            "senior",
            "staff",
            "principal",
            "lead",
            "junior",
            "intern",
            "remote",
            "germany",
            "berlin",
            "munich",
        }
    ]
    return " ".join(tokens)


def _normalize_location_for_dedupe(location: str, country: str | None) -> str:
    location_text = normalize_text(location)
    country_text = normalize_text(country or "")
    if country_text and country_text in location_text:
        return country_text
    if any(city in location_text for city in ["berlin", "munich", "hamburg", "cologne", "frankfurt"]):
        for city in ["berlin", "munich", "hamburg", "cologne", "frankfurt"]:
            if city in location_text:
                return city
    return location_text or country_text or "unknown"


def _prefer_opportunity(current: dict[str, Any], challenger: dict[str, Any]) -> dict[str, Any]:
    def rank(item: dict[str, Any]) -> tuple[float, int, int, int, int]:
        return (
            float(item.get("score_total") or 0),
            1 if item.get("direct_apply_url") else 0,
            1 if item.get("opportunity_kind") == "job" else 0,
            1 if item.get("posted_at") else 0,
            len(item.get("contacts") or []),
        )

    return challenger if rank(challenger) > rank(current) else current


def _merge_duplicate_opportunities(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    merged["contacts"] = _merge_contacts(primary.get("contacts", []), secondary.get("contacts", []))
    merged["score_labels"] = sorted(set([*(primary.get("score_labels") or []), *(secondary.get("score_labels") or [])]))
    merged["score_reasons"] = list(dict.fromkeys([*(primary.get("score_reasons") or []), *(secondary.get("score_reasons") or [])]))[:5]
    merged["saved"] = bool(primary.get("saved") or secondary.get("saved"))
    merged["saved_status"] = primary.get("saved_status") or secondary.get("saved_status")
    merged["saved_opportunity_id"] = primary.get("saved_opportunity_id") or secondary.get("saved_opportunity_id")

    if not merged.get("direct_apply_url"):
        merged["direct_apply_url"] = secondary.get("direct_apply_url")
    if not merged.get("company_careers_url"):
        merged["company_careers_url"] = secondary.get("company_careers_url")
    if not merged.get("company_website_url"):
        merged["company_website_url"] = secondary.get("company_website_url")
    if not merged.get("canonical_job_url"):
        merged["canonical_job_url"] = secondary.get("canonical_job_url")
    if not merged.get("portal_job_url"):
        merged["portal_job_url"] = secondary.get("portal_job_url")
    if not merged.get("posted_at"):
        merged["posted_at"] = secondary.get("posted_at")

    primary_company = primary.get("company") or {}
    secondary_company = secondary.get("company") or {}
    if isinstance(primary_company, dict) or isinstance(secondary_company, dict):
        merged["company"] = {
            **(secondary_company if isinstance(secondary_company, dict) else {}),
            **(primary_company if isinstance(primary_company, dict) else {}),
        }

    citation = dict(primary.get("citation") or {})
    secondary_citation = secondary.get("citation") or {}
    citation["evidence"] = list(
        dict.fromkeys([*(citation.get("evidence") or []), *(secondary_citation.get("evidence") or [])])
    )[:6]
    if not citation.get("canonical_url"):
        citation["canonical_url"] = secondary_citation.get("canonical_url")
    if not citation.get("job_url"):
        citation["job_url"] = secondary_citation.get("job_url")
    merged["citation"] = citation
    return _finalize_merged_opportunity(merged)


def _finalize_merged_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    merged = dict(item)
    company = merged.get("company") or {}
    has_apply_path = bool(merged.get("direct_apply_url") or merged.get("company_careers_url"))
    merged["opportunity_kind"] = "job" if has_apply_path else "outreach_lead"
    if has_apply_path and "Direct Apply" not in (merged.get("score_labels") or []):
        merged["score_labels"] = sorted(set([*(merged.get("score_labels") or []), "Direct Apply"]))
    source_type = merged.get("source_type")
    if source_type == "startup_directory" and isinstance(company, dict) and company.get("dynamic_provider") == "startupmap":
        merged["source_bucket"] = "startupmap"
    elif source_type in {"greenhouse", "lever", "ashby", "ats_discovery"}:
        merged["source_bucket"] = "ats"
    elif source_type == "indeed_search":
        merged["source_bucket"] = "indeed"
    elif source_type == "theirstack_search":
        merged["source_bucket"] = "theirstack"
    elif source_type == "apify_actor":
        merged["source_bucket"] = "apify"
    elif source_type in {"google_web", "web_search"}:
        merged["source_bucket"] = "web"
    elif source_type == "startup_directory":
        merged["source_bucket"] = "crawler"
    elif source_type == "startup_company":
        merged["source_bucket"] = "crawler"
    return merged
