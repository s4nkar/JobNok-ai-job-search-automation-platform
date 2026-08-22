"""Resolves a user-typed company name or pasted careers URL into an ATS
source (type + slug) - the "smart add" flow behind My Sources, so a user
never has to know or care whether a company uses Greenhouse, Lever, or
Ashby, let alone its board slug. See service.py's resolve_startup_hunt_source
for how this plugs into the fast-sync / async-fallback flow.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import httpx

from app.modules.startup_hunt.engine import StartupHuntSourceConfig
from app.modules.startup_hunt.providers import ashby, greenhouse, lever

_ATS_PROVIDERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}

_ATS_URL_PATTERNS = {
    "greenhouse": re.compile(r"(?:job-)?boards(?:-api)?\.greenhouse\.io/(?:v1/boards/)?([a-zA-Z0-9_-]+)", re.I),
    "lever": re.compile(r"jobs\.lever\.co/([a-zA-Z0-9_-]+)", re.I),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)", re.I),
}

# ATS platforms we can detect on a careers page but don't actually support
# fetching from (see providers/__init__.py's module docstring for why the
# supported list stops at greenhouse/lever/ashby). Not currently surfaced
# as a distinct error message anywhere - kept as a named list so that day
# (a "this company uses Workday, not supported yet" message) is a one-line
# change, not a re-discovery.
_UNSUPPORTED_ATS_MARKERS = (
    "myworkdayjobs.com", "workable.com", "smartrecruiters.com",
    "teamtailor.com", "personio.de", "kenjo.io", "join.com",
)


@dataclass
class ResolvedSource:
    type: str
    slug: str
    url: str | None = None


def slugify(name: str) -> str:
    """One canonical slug guess from a company name - lowercase,
    alphanumeric-and-hyphens only, collapsed. Good enough to hit the common
    case (most companies' ATS slug is exactly their name, slugified) - the
    async fallback tries more variants for the rest (see slug_variants)."""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def slug_variants(name: str) -> list[str]:
    """A handful of additional candidate slugs beyond the one canonical
    guess slugify() makes - tried by the async fallback resolver only, not
    the fast sync path (see resolve_source's ~3s timeout budget). Order
    matters, most-likely first."""
    base = slugify(name)
    variants = [base, base.replace("-", "")]
    lowered = name.strip().lower()
    for suffix in (" inc", " ai", " labs", " technologies", " technology", " the"):
        if lowered.endswith(suffix):
            trimmed = slugify(name[: -len(suffix)])
            if trimmed:
                variants.append(trimmed)
                variants.append(trimmed.replace("-", ""))
    seen: set[str] = set()
    ordered: list[str] = []
    for value in variants:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _match_ats_url(text: str) -> ResolvedSource | None:
    for ats_type, pattern in _ATS_URL_PATTERNS.items():
        match = pattern.search(text)
        if match:
            return ResolvedSource(type=ats_type, slug=match.group(1))
    return None


async def _probe_slug(client: httpx.AsyncClient, ats_type: str, slug: str, company: str) -> bool:
    """True if `slug` is a real board on this ATS - reuses the same
    provider fetch() the live search pipeline calls, so "does this board
    exist" and "can we actually fetch jobs from it" never diverge. A 200
    with zero current job postings still counts as a real board (worth
    watching for future postings), only a 404/error counts as a miss."""
    provider = _ATS_PROVIDERS[ats_type]
    source = StartupHuntSourceConfig(type=ats_type, name=company, company=company, slug=slug)
    try:
        await provider.fetch(client, source)
        return True
    except Exception:
        return False


async def _scan_careers_page_for_ats(client: httpx.AsyncClient, url: str) -> ResolvedSource | None:
    """Fetches a company's own careers page and scans its HTML for a link
    to a known ATS - handles the common case where a pasted careers URL is
    the company's own domain (e.g. acme.com/careers), which just embeds or
    links out to their actual Greenhouse/Lever/Ashby board."""
    try:
        response = await client.get(url, timeout=8.0, follow_redirects=True)
        response.raise_for_status()
    except Exception:
        return None
    return _match_ats_url(response.text)


async def try_direct_resolve(company_input: str) -> ResolvedSource | None:
    """The fast, synchronous resolution path - one direct slug guess (or a
    pasted URL's own ATS pattern / careers-page scan) tried against
    Greenhouse/Lever/Ashby in parallel. None means "didn't resolve yet,"
    not "will never resolve" - the caller falls through to the async
    multi-variant fallback (see try_fallback_resolve) rather than failing
    outright.
    """
    value = company_input.strip()
    async with httpx.AsyncClient(timeout=10.0) as client:
        if value.lower().startswith(("http://", "https://")):
            direct = _match_ats_url(value)
            candidate = direct or await _scan_careers_page_for_ats(client, value)
            if not candidate:
                return None
            ok = await _probe_slug(client, candidate.type, candidate.slug, value)
            return candidate if ok else None

        slug = slugify(value)
        if not slug:
            return None
        checks = await asyncio.gather(
            *(_probe_slug(client, ats_type, slug, value) for ats_type in _ATS_PROVIDERS)
        )
        for ats_type, ok in zip(_ATS_PROVIDERS, checks):
            if ok:
                return ResolvedSource(type=ats_type, slug=slug)
        return None


async def try_fallback_resolve(company_input: str) -> ResolvedSource | None:
    """The slower async-fallback resolution path, run in the background
    (see tasks.py) after the fast path's tighter sync budget didn't land a
    match - either because there genuinely wasn't one with a single guess,
    or because a slow careers-page fetch got cut off by that budget.
    Retries try_direct_resolve's own URL-handling with a fresh, un-timed-out
    execution context (a background task has no ~3s budget to race), then
    tries several more slug variants than the fast path's one guess for a
    plain company name.
    """
    resolved = await try_direct_resolve(company_input)
    if resolved is not None:
        return resolved

    value = company_input.strip()
    if value.lower().startswith(("http://", "https://")):
        return None  # already retried in full just above

    # All variant x ATS-type combinations in parallel, not sequential - a
    # handful of variants times 3 ATS types is a small enough burst to fire
    # at once, and sequential 10s-timeout-each calls could otherwise blow
    # past the ARQ worker's job_timeout in the worst case.
    candidates = [(slug, ats_type) for slug in slug_variants(value) for ats_type in _ATS_PROVIDERS]
    async with httpx.AsyncClient(timeout=10.0) as client:
        checks = await asyncio.gather(
            *(_probe_slug(client, ats_type, slug, value) for slug, ats_type in candidates)
        )
    for (slug, ats_type), ok in zip(candidates, checks):
        if ok:
            return ResolvedSource(type=ats_type, slug=slug)
    return None
