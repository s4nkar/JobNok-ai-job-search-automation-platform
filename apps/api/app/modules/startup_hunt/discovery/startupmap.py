"""StartupMap discovery source (PRD sections 9, 39).

Off by default (settings.startup_hunt_startupmap_enabled). robots.txt and
/llms.txt at startupmap.one both explicitly welcome crawlers/AI ("Search
engines and AI crawlers are welcome to crawl and cite the site"; robots.txt
only disallows /admin/, /api, /settings, none of which this touches) - but no
separate Terms of Service could be located: checked the sitemap (only
/privacy is listed, no /terms), llms.txt (no terms link), and the homepage's
raw HTML (a client-rendered SPA shell with no footer links reachable without
executing JS). That gap should be explicitly accepted, or resolved (e.g. by
contacting them directly - they have /partner and /advertise pages, so this
looks like a business open to that conversation), before this flag is ever
flipped on in production.

Site structure (verified directly against the live site, not assumed):
- The homepage/map views are fully client-rendered - no company data in
  static HTML at all, so fetching them (the original version of this file
  did) finds nothing.
- The real per-company data lives on ~4,500 individual, server-rendered
  pages at /startup/{slug}, cleanly enumerated by /sitemap.xml.
- Each page's structured data is schema.org JSON-LD wrapped in a single
  `@graph` array (not a bare object/list) containing two entries: an
  Organization for StartupMap itself (skipped) and one for the actual
  startup, with `location.address` (not a bare `address`) for city/country.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from typing import Any

from app.core.config import settings
from app.modules.startup_hunt.discovery.startup_source import DiscoveredStartup
from app.modules.startup_hunt.engine import extract_domain
from app.modules.startup_hunt.ingestion.ssrf_guard import SSRFBlockedError, safe_fetch

logger = logging.getLogger(__name__)

_JSON_LD_PATTERN = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S
)
_STARTUP_PAGE_PATTERN = re.compile(r"/startup/([a-zA-Z0-9_-]+)$")
_LOC_PATTERN = re.compile(r"<loc>([^<]+)</loc>")

_DISCOVERY_SOURCE = "startupmap"
_BASE_URL = "https://startupmap.one"
_SITEMAP_URL = f"{_BASE_URL}/sitemap.xml"
# Identifies honestly rather than spoofing a browser - startupmap.one has
# explicitly said crawlers/AI are welcome, and an identifiable UA is what
# lets them selectively rate-limit or block this specifically if they ever
# need to, unlike an anonymous default would.
_HEADERS = {"User-Agent": "JobNokBot/1.0 (+https://jobnok.app; startup discovery)"}


def is_available() -> bool:
    return settings.startup_hunt_startupmap_enabled


def _extract_graph_entries(html: str) -> list[dict[str, Any]]:
    """Every JSON-LD block's @graph entries, flattened. StartupMap wraps each
    page's structured data in one `@graph` array per <script> block rather
    than a bare object - falls back to treating the block itself as a single
    entry (or a bare list of entries) in case a future page doesn't use
    @graph. Best-effort: malformed JSON or an unexpected shape is skipped,
    never raised - one bad block must not fail the whole discovery run."""
    entries: list[dict[str, Any]] = []
    for match in _JSON_LD_PATTERN.finditer(html):
        try:
            data = json.loads(match.group(1).strip())
        except (json.JSONDecodeError, AttributeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            entries.extend(item for item in data["@graph"] if isinstance(item, dict))
        elif isinstance(data, dict):
            entries.append(data)
        elif isinstance(data, list):
            entries.extend(item for item in data if isinstance(item, dict))
    return entries


def _to_discovered(slug: str, org: dict[str, Any]) -> DiscoveredStartup | None:
    name = str(org.get("name") or "").strip()
    if not name or name == "StartupMap":
        return None  # the site's own Organization entry (always present), not a discovered startup
    website_url = str(org.get("url") or "").strip() or None
    location = org.get("location") if isinstance(org.get("location"), dict) else {}
    address = location.get("address") if isinstance(location.get("address"), dict) else {}
    return DiscoveredStartup(
        name=name,
        domain=extract_domain(website_url),
        website_url=website_url,
        country=str(address.get("addressCountry") or "").strip() or None,
        city=str(address.get("addressLocality") or "").strip() or None,
        discovery_source=_DISCOVERY_SOURCE,
        discovery_source_url=f"{_BASE_URL}/startup/{slug}",
        discovery_source_id=slug,
    )


async def _fetch_startup_slugs() -> list[str]:
    """One request for the whole sitemap, filtered down to /startup/{slug}
    detail-page URLs only - /startups/, /jobs/, /map/ and other sections are
    ignored (unverified content, out of scope for company discovery)."""
    try:
        xml = await safe_fetch(_SITEMAP_URL, headers=_HEADERS)
    except SSRFBlockedError:
        logger.exception("StartupMap sitemap fetch blocked by SSRF guard")
        return []
    except Exception:
        logger.exception("StartupMap sitemap fetch failed")
        return []

    slugs = []
    for loc in _LOC_PATTERN.findall(xml):
        match = _STARTUP_PAGE_PATTERN.search(loc)
        if match:
            slugs.append(match.group(1))
    return slugs


async def _fetch_one(slug: str, semaphore: asyncio.Semaphore) -> DiscoveredStartup | None:
    url = f"{_BASE_URL}/startup/{slug}"
    async with semaphore:
        try:
            html = await safe_fetch(url, headers=_HEADERS)
        except SSRFBlockedError:
            logger.warning("StartupMap page fetch blocked by SSRF guard: %s", url)
            return None
        except Exception:
            logger.exception("StartupMap page fetch failed: %s", url)
            return None

    for entry in _extract_graph_entries(html):
        if entry.get("@type") == "Organization":
            discovered = _to_discovered(slug, entry)
            if discovered is not None:
                return discovered
    return None


class StartupMapSource:
    """known_slugs: discovery_source_ids (StartupMap slugs) already on record
    in company_registry - passed in by discovery_worker.py, which is the one
    with DB access (this class deliberately isn't - see StartupSource's
    docstring). Excluded from sampling so every fetch this run is guaranteed
    new ground, not a random re-roll that might land on an already-known
    company. Without this, random sampling alone means full coverage of the
    ~4,500 listed startups would take roughly N*ln(N) fetches to complete in
    expectation (the "coupon collector" effect - later runs increasingly
    re-draw already-known slugs), not the N you'd naively expect - for 4,500
    startups that's the difference between ~45 days and closer to a year at
    100 fetches/day. Excluding known ones makes every run genuine forward
    progress instead, so it's a straight N/batch_size runs to full coverage.
    """

    name = _DISCOVERY_SOURCE

    def __init__(self, known_slugs: set[str] | None = None):
        self._known_slugs = known_slugs or set()

    async def discover(self) -> list[DiscoveredStartup]:
        if not is_available():
            return []

        slugs = await _fetch_startup_slugs()
        if not slugs:
            logger.warning(
                "StartupMap sitemap returned zero /startup/ pages - verify the site "
                "structure hasn't changed (see this module's docstring)."
            )
            return []

        remaining = [slug for slug in slugs if slug not in self._known_slugs]
        if not remaining:
            logger.info("StartupMap discovery: every listed startup is already known - nothing new to fetch.")
            return []

        # Random sample of whatever's left, not always the first N
        # alphabetically - avoids any systematic bias in which unknown
        # startups get picked up first across runs.
        sample_size = min(len(remaining), settings.startup_hunt_discovery_batch_size)
        sampled_slugs = random.sample(remaining, sample_size)

        semaphore = asyncio.Semaphore(settings.startup_hunt_startupmap_fetch_concurrency)
        results = await asyncio.gather(*(_fetch_one(slug, semaphore) for slug in sampled_slugs))
        return [item for item in results if item is not None]
