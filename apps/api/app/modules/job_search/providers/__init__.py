"""Job provider registry.

Adding a provider = write providers/<name>.py exposing fetch/is_available/
supports_country, then add one ProviderSpec entry to PROVIDERS below.
Nothing in service.py, scoring.py, or dedup.py needs to change.

Arbeitnow is deliberately NOT in PROVIDERS - it has no country field, so it
can never reliably participate in this location-filtered/ranked pipeline.
It's fetched separately by service.py's bonus-jobs path instead (title match
only, no location filtering), which calls providers.arbeitnow directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.core.config import settings
from app.modules.job_search.providers import adzuna, bundesagentur
from app.modules.job_search.providers.base import ProviderError, RawJobListing, canonicalize_job_url

__all__ = [
    "ProviderError", "RawJobListing", "canonicalize_job_url", "ProviderSpec", "PROVIDERS",
    "applicable_providers",
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
    # own per-day cap. None = no global budget enforced.
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
]


def applicable_providers(country: str | None, location: str | None) -> list[ProviderSpec]:
    """Providers worth calling for this search - configured (has API keys)
    and geographically applicable (e.g. skip a Germany-only provider for a
    US search) - filtered before any network call, not after a failed one."""
    return [p for p in PROVIDERS if p.is_available() and p.supports_country(country, location)]
