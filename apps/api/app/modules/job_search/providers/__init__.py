"""Job provider registry.

Adding a provider = write providers/<name>.py exposing fetch/is_available/
supports_country, then add one ProviderSpec entry to PROVIDERS below.
Nothing in service.py, scoring.py, or dedup.py needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.modules.job_search.providers import adzuna, arbeitnow, bundesagentur
from app.modules.job_search.providers.base import ProviderError, RawJobListing, canonicalize_job_url
from app.services.cache import delete_cached, get_cached, increment_with_ttl, set_cached

__all__ = [
    "ProviderError", "RawJobListing", "canonicalize_job_url", "ProviderSpec", "PROVIDERS",
    "applicable_providers", "circuit_is_open", "record_provider_result",
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


PROVIDERS: list[ProviderSpec] = [
    ProviderSpec(
        name="adzuna",
        fetch=adzuna.fetch,
        is_available=adzuna.is_available,
        supports_country=adzuna.supports_country,
        is_metered=True,
    ),
    ProviderSpec(
        name="bundesagentur",
        fetch=bundesagentur.fetch,
        is_available=bundesagentur.is_available,
        supports_country=bundesagentur.supports_country,
    ),
    ProviderSpec(
        name="arbeitnow",
        fetch=arbeitnow.fetch,
        is_available=arbeitnow.is_available,
        supports_country=arbeitnow.supports_country,
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
