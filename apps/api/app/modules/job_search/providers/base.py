"""Shared contract every job provider fetches into - so nothing outside a
provider's own file needs to know that provider's native API shape."""

from __future__ import annotations

from typing import TypedDict
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


class RawJobMetadata(TypedDict, total=False):
    country: str | None
    salary_min: float | None
    salary_max: float | None
    category: str | None
    # Explicit remote flag, when a provider's own data has one (e.g. Arbeitnow)
    # - scoring._score_job already falls back to this when the location text
    # itself doesn't contain "remote".
    remote: bool


class RawJobListing(TypedDict):
    source_name: str
    provider_type: str
    external_job_id: str | None
    company: str
    role: str
    location: str
    job_url: str
    job_url_canonical: str
    # ISO string, not a datetime - raw listings round-trip through the Redis
    # response cache as JSON.
    posted_at: str | None
    description_text: str
    metadata: RawJobMetadata


class ProviderError(Exception):
    """Raised by a provider's fetch() for missing config, an unsupported
    country/region, or an upstream failure (timeout, 401/429/5xx, etc).

    Callers treat all of these uniformly: if another provider or the DB cache
    already has results to show, degrade gracefully and drop this provider's
    contribution; if nothing else has results either, surface str(exc) to the
    user as a 400.
    """


def canonicalize_job_url(url: str) -> str:
    """Strips tracking params / fragment and lowercases scheme+host, so the
    same listing fetched twice (DB cache vs. live re-fetch, or via a search
    result vs. an apply-tracking snapshot) collapses to one fingerprint."""
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
