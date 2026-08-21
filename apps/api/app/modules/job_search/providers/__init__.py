"""Job provider registry.

Adding a provider = write providers/<name>.py exposing fetch/is_available/
supports_country, then add one ProviderSpec entry to PROVIDERS below.
Nothing in service.py, scoring.py, or dedup.py needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from app.core.config import settings
from app.modules.job_search.providers import adzuna, arbeitnow, bundesagentur
from app.modules.job_search.providers.base import ProviderError, RawJobListing, canonicalize_job_url
from app.services.cache import delete_cached, get_cached, increment_with_ttl, set_cached

__all__ = [
    "ProviderError", "RawJobListing", "canonicalize_job_url", "ProviderSpec", "PROVIDERS",
    "applicable_providers", "circuit_is_open", "record_provider_result",
    "check_provider_budget", "check_tool_budget",
]


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    fetch: Callable[[dict[str, Any]], Awaitable[list[dict[str, Any]]]]
    is_available: Callable[[], bool]
    # Takes the search's raw country and location text (same free-form input
    # the request gives) - each provider resolves that itself, since alias
    # tables/geographic coverage differ per provider.
    supports_country: Callable[[str | None, str | None], bool]
    # True for a provider with a real external usage quota/cost (e.g. Adzuna's
    # metered API) - service.py fetches free providers first and only calls
    # metered ones for whatever shortfall remains, instead of always fanning
    # out to every applicable provider regardless of whether it's needed.
    is_metered: bool = False
    # Global daily call cap shared across every user, distinct from any
    # per-user limit - protects the provider's own account-level quota from
    # aggregate exhaustion even when each individual user is well under their
    # own per-day cap. None = no global budget enforced (unmetered/no fixed
    # external quota, e.g. Bundesagentur, Arbeitnow).
    daily_budget: int | None = None


PROVIDERS: list[ProviderSpec] = [
    ProviderSpec(
        name="adzuna",
        fetch=adzuna.fetch,
        is_available=adzuna.is_available,
        supports_country=adzuna.supports_country,
        is_metered=True,
        daily_budget=settings.adzuna_daily_call_budget,
    ),
    ProviderSpec(
        name="bundesagentur",
        fetch=bundesagentur.fetch,
        is_available=bundesagentur.is_available,
        supports_country=bundesagentur.supports_country,
        daily_budget=settings.bundesagentur_daily_call_budget,
    ),
    ProviderSpec(
        name="arbeitnow",
        fetch=arbeitnow.fetch,
        is_available=arbeitnow.is_available,
        supports_country=arbeitnow.supports_country,
        daily_budget=settings.arbeitnow_daily_call_budget,
    ),
]


def applicable_providers(country: str | None, location: str | None) -> list[ProviderSpec]:
    """Providers worth calling for this search - configured (has API keys)
    and geographically applicable (e.g. skip a Germany-only provider for a
    US search) - filtered before any network call, not after a failed one."""
    return [p for p in PROVIDERS if p.is_available() and p.supports_country(country, location)]


# ── Per-provider circuit breaker ────────────────────────────────────────
# If a provider starts hard-failing repeatedly (e.g. an unofficial API
# breaking, like Bundesagentur's /pc/v4 -> /pc/v6 move), every affected
# search would otherwise still pay the full request timeout on a call
# that's essentially guaranteed to fail, until someone notices and flips
# the provider's kill switch by hand. This trips automatically instead.
_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_FAILURE_WINDOW_SECONDS = 300  # rolling window failures are counted in
_CIRCUIT_OPEN_COOLDOWN_SECONDS = 180  # once tripped, skip live calls for this long


def _circuit_open_key(provider_name: str) -> str:
    return f"job_search:circuit:{provider_name}:open"


def _circuit_fail_key(provider_name: str) -> str:
    return f"job_search:circuit:{provider_name}:fail_count"


async def circuit_is_open(provider_name: str) -> bool:
    """True if this provider has failed repeatedly recently and should be
    skipped without a network call. Fails open (False) on a Redis error - a
    broken circuit breaker must never block a provider that might be healthy."""
    try:
        return bool(await get_cached(_circuit_open_key(provider_name)))
    except Exception:
        return False


async def record_provider_result(provider_name: str, *, ok: bool) -> None:
    """Feed a live fetch's outcome into the provider's circuit breaker. A
    success resets the failure count immediately - one good response is
    enough to trust the provider again, no need to wait out the window.
    Best-effort throughout: a tracking failure must never break the search."""
    try:
        if ok:
            await delete_cached(_circuit_fail_key(provider_name))
            return
        count = await increment_with_ttl(_circuit_fail_key(provider_name), _CIRCUIT_FAILURE_WINDOW_SECONDS)
        if count >= _CIRCUIT_FAILURE_THRESHOLD:
            await set_cached(_circuit_open_key(provider_name), "1", _CIRCUIT_OPEN_COOLDOWN_SECONDS)
    except Exception:
        pass


# ── Per-provider global daily budget ────────────────────────────────────
# Distinct from the circuit breaker (reacts to failures) and the per-user
# daily quota (doesn't aggregate across users) - this protects a metered
# provider's own account-level quota from being exhausted by the aggregate
# of many individually-compliant users, the same failure shape as the
# Upstash Redis quota exhaustion hit earlier this project (a shared external
# resource exhausted by legitimate use, not abuse).


def _budget_key(provider_name: str) -> str:
    return f"job_search:provider_budget:{provider_name}"


def _seconds_until_midnight_utc() -> int:
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return int((midnight - now).total_seconds())


async def check_provider_budget(provider: ProviderSpec) -> bool:
    """True if this provider is still within its global daily call budget.
    None budget = unmetered, always True (and skips Redis entirely). Resets
    at midnight UTC, matching the per-user daily quota's reset convention.
    INCR-first (same race-avoidance reasoning as check_rate_limit) - this
    must be called immediately before an actual fetch attempt, once per
    attempt, not speculatively. Fails open on a Redis error - a broken
    budget tracker must never block a provider that might have budget left."""
    if provider.daily_budget is None:
        return True
    try:
        count = await increment_with_ttl(_budget_key(provider.name), _seconds_until_midnight_utc())
        return count <= provider.daily_budget
    except Exception:
        return True


_TOOL_BUDGET_KEY = "job_search:tool_budget"


async def check_tool_budget() -> bool:
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
        count = await increment_with_ttl(_TOOL_BUDGET_KEY, _seconds_until_midnight_utc())
        return count <= settings.job_search_tool_daily_budget
    except Exception:
        return True
