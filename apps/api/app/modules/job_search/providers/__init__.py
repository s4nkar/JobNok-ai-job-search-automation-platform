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

__all__ = ["ProviderError", "RawJobListing", "canonicalize_job_url", "ProviderSpec", "PROVIDERS", "applicable_providers"]


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    fetch: Callable[[dict[str, Any]], Awaitable[list[dict[str, Any]]]]
    is_available: Callable[[], bool]
    # Takes the search's raw country and location text (same free-form input
    # the request gives) - each provider resolves that itself, since alias
    # tables/geographic coverage differ per provider.
    supports_country: Callable[[str | None, str | None], bool]


PROVIDERS: list[ProviderSpec] = [
    ProviderSpec(
        name="adzuna",
        fetch=adzuna.fetch,
        is_available=adzuna.is_available,
        supports_country=adzuna.supports_country,
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
