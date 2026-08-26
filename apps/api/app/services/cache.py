"""Upstash Redis client for rate limiting and caching.

Uses the Upstash REST API (HTTP-based) rather than a persistent TCP connection,
which works correctly in Railway's serverless-style environment.
"""

import hashlib
import json
import random
import time
import uuid
import httpx
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from app.core.config import settings


class UpstashRedisError(Exception):
    """Raised on an Upstash REST API command-level error (e.g. quota exceeded).

    Upstash returns these as a 200 OK with an {"error": ...} body, not an HTTP
    error status, so httpx never raises on its own. Without this, every
    UpstashRedis method below silently returned its default (0, None, -1) on
    ANY command failure, indistinguishable from a legitimately empty result -
    which is exactly how a quota-exhausted Redis account made rate limiting
    silently report "unlimited" instead of failing loudly or failing open via
    the callers' own except-Exception handling.
    """


class UpstashRedis:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}

    async def _cmd(self, *args) -> dict:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                self.url,
                headers=self.headers,
                json=list(args),
            )
            res.raise_for_status()
            body = res.json()
            if "error" in body:
                raise UpstashRedisError(body["error"])
            return body

    async def get(self, key: str) -> str | None:
        result = await self._cmd("GET", key)
        return result.get("result")

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        if ex:
            await self._cmd("SET", key, value, "EX", ex)
        else:
            await self._cmd("SET", key, value)

    async def incr(self, key: str) -> int:
        result = await self._cmd("INCR", key)
        return result.get("result", 0)

    async def expire(self, key: str, seconds: int) -> None:
        await self._cmd("EXPIRE", key, seconds)

    async def ttl(self, key: str) -> int:
        result = await self._cmd("TTL", key)
        return result.get("result", -1)

    async def delete(self, key: str) -> None:
        await self._cmd("DEL", key)

    async def set_nx(self, key: str, value: str, ex: int) -> bool:
        """SET key value NX EX ex — sets only if the key doesn't already exist.
        Returns True if this call set it (lock acquired), False if it was
        already set (someone else holds it). Upstash returns a null result
        for a failed NX, distinct from the {"result": "OK"} of a real set."""
        result = await self._cmd("SET", key, value, "NX", "EX", ex)
        return result.get("result") is not None

    async def zadd(self, key: str, score: float, member: str) -> None:
        await self._cmd("ZADD", key, score, member)

    async def zremrangebyscore(self, key: str, min_score: str, max_score: str) -> None:
        await self._cmd("ZREMRANGEBYSCORE", key, min_score, max_score)

    async def zcard(self, key: str) -> int:
        result = await self._cmd("ZCARD", key)
        return result.get("result", 0)


def _get_redis() -> UpstashRedis:
    return UpstashRedis(
        url=settings.upstash_redis_rest_url,
        token=settings.upstash_redis_rest_token,
    )


def _midnight_utc_seconds() -> int:
    """Seconds until midnight UTC — used for daily rate limit TTL."""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    next_midnight = midnight + timedelta(days=1)
    return int((next_midnight - now).total_seconds())


async def check_rate_limit(user_id: str, tool: str, limit: int) -> tuple[bool, int]:
    """Check if user has exceeded their daily rate limit for a tool.

    Uses INCR-first to avoid a GET→compare→INCR race condition where two
    concurrent requests could both read count < limit and both be allowed.
    TTL is set unconditionally after every increment so an EXPIRE failure
    on the first increment never leaves the key without a TTL.

    Returns:
        (allowed: bool, remaining: int)
    """
    redis = _get_redis()
    key = f"rl:{user_id}:{tool}"

    new_count = await redis.incr(key)
    ttl_seconds = _midnight_utc_seconds()
    await redis.expire(key, ttl_seconds)

    if new_count > limit:
        return False, 0

    return True, max(0, limit - new_count)


async def check_burst_limit(user_id: str, tool: str, limit: int, window_seconds: int) -> bool:
    """Short burst limit, separate from check_rate_limit's daily quota -
    protects against rapid-fire requests (double-click, a retry loop, a
    search box with no debounce) within the same day's allowance, which the
    daily quota alone doesn't address since it only caps total volume, not
    arrival rate.

    A sliding-window LOG (a sorted set keyed by each request's own
    timestamp), not a fixed window - a fixed window (INCR+EXPIRE on one
    window-aligned key, what this used to do) lets `limit` requests through
    right before a window boundary and `limit` more right after, doubling
    the effective burst exactly at the boundary a retry loop is likely to
    straddle. This prunes anything older than window_seconds, adds the
    current request, then counts what's left - an exact trailing-window
    count, not a boundary-aligned approximation.

    The prune/add/count calls aren't atomic (Upstash's REST API has no
    multi-command transaction here), so there's a small race under true
    concurrency - acceptable for a guard this low-volume (3 req/10s) and
    this coarse by design (stop obvious retry storms, not a hard security
    boundary), same fail-open philosophy as every other limiter in this
    file.
    """
    redis = _get_redis()
    key = f"rl_burst:{user_id}:{tool}"
    now_ms = time.time() * 1000
    cutoff_ms = now_ms - (window_seconds * 1000)
    await redis.zremrangebyscore(key, "-inf", f"{cutoff_ms:.3f}")
    await redis.zadd(key, now_ms, f"{now_ms:.3f}:{uuid.uuid4().hex}")
    await redis.expire(key, window_seconds)
    count = await redis.zcard(key)
    return count <= limit


# ── Per-provider circuit breaker ────────────────────────────────────────
# If a provider starts hard-failing repeatedly (e.g. an unofficial API
# breaking shape), every affected search would otherwise still pay the full
# request timeout on a call that's essentially guaranteed to fail, until
# someone notices and flips the provider's kill switch by hand. This trips
# automatically instead. Originally job_search-only (job_search/providers/
# __init__.py); moved here and given a `scope` param (e.g. "job_search",
# "startup_hunt") when startup_hunt needed the same protection too, so two
# tools' providers of the same name (unlikely, but not impossible) never
# share circuit-breaker state.
_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_FAILURE_WINDOW_SECONDS = 300  # rolling window failures are counted in
_CIRCUIT_OPEN_COOLDOWN_SECONDS = 180  # once tripped, skip live calls for this long


def _circuit_open_key(scope: str, provider_name: str) -> str:
    return f"{scope}:circuit:{provider_name}:open"


def _circuit_fail_key(scope: str, provider_name: str) -> str:
    return f"{scope}:circuit:{provider_name}:fail_count"


async def circuit_is_open(scope: str, provider_name: str) -> bool:
    """True if this provider has failed repeatedly recently and should be
    skipped without a network call. Fails open (False) on a Redis error - a
    broken circuit breaker must never block a provider that might be healthy."""
    try:
        return bool(await get_cached(_circuit_open_key(scope, provider_name)))
    except Exception:
        return False


async def get_circuit_state(scope: str, provider_name: str) -> dict:
    """Read-only snapshot of a provider's circuit breaker state, for
    observability display (see app/modules/admin/service.py) - never used in
    the hot request path, that's circuit_is_open above. Fails open to a
    healthy-looking default on a Redis error, same as every other function
    in this file - a broken read here must never make a fine provider look
    tripped on a dashboard."""
    try:
        is_open = bool(await get_cached(_circuit_open_key(scope, provider_name)))
        fail_count_raw = await get_cached(_circuit_fail_key(scope, provider_name))
        recent_failures = int(fail_count_raw) if fail_count_raw else 0
        return {"provider": provider_name, "open": is_open, "recent_failures": recent_failures}
    except Exception:
        return {"provider": provider_name, "open": False, "recent_failures": 0}


async def record_provider_result(scope: str, provider_name: str, *, ok: bool) -> None:
    """Feed a live fetch's outcome into the provider's circuit breaker. A
    success resets the failure count immediately - one good response is
    enough to trust the provider again, no need to wait out the window.
    Best-effort throughout: a tracking failure must never break the search."""
    try:
        if ok:
            await delete_cached(_circuit_fail_key(scope, provider_name))
            return
        count = await increment_with_ttl(_circuit_fail_key(scope, provider_name), _CIRCUIT_FAILURE_WINDOW_SECONDS)
        if count >= _CIRCUIT_FAILURE_THRESHOLD:
            await set_cached(_circuit_open_key(scope, provider_name), "1", _CIRCUIT_OPEN_COOLDOWN_SECONDS)
    except Exception:
        pass


# ── Per-provider global daily budget + whole-tool daily budget ─────────
# Distinct from the circuit breaker (reacts to failures) and any per-user
# daily quota (doesn't aggregate across users) - this protects a metered
# provider's own account-level quota (check_provider_budget) and a tool's
# overall external-call volume (check_tool_budget) from being exhausted by
# the aggregate of many individually-compliant users. Same move/genericize
# history as the circuit breaker above.


def _budget_key(scope: str, provider_name: str) -> str:
    return f"{scope}:provider_budget:{provider_name}"


async def check_provider_budget(scope: str, provider_name: str, daily_budget: int | None) -> bool:
    """True if this provider is still within its global daily call budget.
    None budget = unmetered, always True (and skips Redis entirely). Resets
    at midnight UTC, matching the per-user daily quota's reset convention.
    INCR-first (same race-avoidance reasoning as check_rate_limit) - this
    must be called immediately before an actual fetch attempt, once per
    attempt, not speculatively. Fails open on a Redis error - a broken
    budget tracker must never block a provider that might have budget left."""
    if daily_budget is None:
        return True
    try:
        count = await increment_with_ttl(_budget_key(scope, provider_name), _midnight_utc_seconds())
        return count <= daily_budget
    except Exception:
        return True


async def check_tool_budget(scope: str, daily_budget: int) -> bool:
    """Whole-tool external-call budget, combined across every provider - a
    cost-governance ceiling distinct from any single provider's own quota.
    Catches aggregate cost growth that no per-provider budget would (e.g. a
    provider with no hard external quota of its own still costs real
    bandwidth/DB writes/compute at volume). Checked alongside each
    provider's own circuit breaker/budget, so a call only proceeds once it
    clears its own provider's gates AND this shared tool-wide one. Resets
    midnight UTC. Fails open on a Redis error - a broken budget tracker must
    never block a call that might be fine."""
    try:
        count = await increment_with_ttl(f"{scope}:tool_budget", _midnight_utc_seconds())
        return count <= daily_budget
    except Exception:
        return True


async def get_cached(key: str) -> str | None:
    redis = _get_redis()
    return await redis.get(key)


async def set_cached(key: str, value: str, ttl_seconds: int) -> None:
    redis = _get_redis()
    await redis.set(key, value, ex=ttl_seconds)


def jittered_ttl(base_seconds: int, jitter_fraction: float = 0.15) -> int:
    """Randomize a cache TTL by +/-jitter_fraction so entries written around
    the same time (e.g. everyone's response cache filling up during a burst
    of traffic on a popular query) don't all expire at the same instant -
    reduces the odds of a stampede forming in the first place. Any caller
    with its own single-flight lock (acquire_lock below) already handles a
    stampede gracefully if one forms anyway; this is a cheap complement, not
    a replacement for it."""
    jitter = base_seconds * jitter_fraction
    return max(1, int(base_seconds + random.uniform(-jitter, jitter)))


async def delete_cached(key: str) -> None:
    redis = _get_redis()
    await redis.delete(key)


async def increment_with_ttl(key: str, ttl_seconds: int) -> int:
    """INCR a counter, refreshing its TTL on every increment — same INCR-first
    pattern as check_rate_limit (avoids a GET-then-INCR race), generalized for
    any rolling-window counting use (e.g. per-provider failure counts)."""
    redis = _get_redis()
    new_count = await redis.incr(key)
    await redis.expire(key, ttl_seconds)
    return new_count


async def acquire_lock(key: str, ttl_seconds: int) -> bool:
    """Single-flight lock: True if this call acquired it, False if another
    caller already holds it. Never explicitly released - it just expires
    after ttl_seconds, which avoids a release-that-isn't-mine race (Upstash's
    REST API doesn't offer a simple compare-and-delete) at the cost of a
    slightly longer window before the key is free again. Fine for its use
    (preventing a thundering herd during a several-second fetch), not fine
    for anything needing a hard mutual-exclusion guarantee."""
    redis = _get_redis()
    return await redis.set_nx(key, "1", ttl_seconds)


async def cached_prompt_parse(
    namespace: str,
    prompt: str,
    ttl_seconds: int,
    parse_fn: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Cache the structured-JSON result of parsing a free-text prompt (e.g.
    job_search's preferences_prompt, startup_hunt's strategy_prompt) via an
    LLM call. Same prompt text always extracts to the same filters, so
    there's no reason to re-hit the LLM on every request for identical or
    repeated input. Namespaced per caller so two tools' prompts never
    collide even if the text happens to match.

    Fails open on any cache error (get or set) - a cache miss/write failure
    just means paying the LLM call again, never a broken response.
    """
    key = f"prompt_parse:{namespace}:{hashlib.sha256(prompt.strip().lower().encode('utf-8')).hexdigest()}"

    try:
        cached = await get_cached(key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    result = await parse_fn()

    try:
        await set_cached(key, json.dumps(result), ttl_seconds)
    except Exception:
        pass

    return result
