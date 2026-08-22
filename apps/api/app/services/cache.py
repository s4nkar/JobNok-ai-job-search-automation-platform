"""Upstash Redis client for rate limiting and caching.

Uses the Upstash REST API (HTTP-based) rather than a persistent TCP connection,
which works correctly in Railway's serverless-style environment.
"""

import hashlib
import json
import random
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
    """Short fixed-window burst limit, separate from check_rate_limit's daily
    quota - protects against rapid-fire requests (double-click, a retry loop,
    a search box with no debounce) within the same day's allowance, which the
    daily quota alone doesn't address since it only caps total volume, not
    arrival rate. Same INCR-first pattern as check_rate_limit, just a much
    shorter window (e.g. 3 requests / 10 seconds instead of N / day)."""
    key = f"rl_burst:{user_id}:{tool}:{window_seconds}"
    count = await increment_with_ttl(key, window_seconds)
    return count <= limit


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
