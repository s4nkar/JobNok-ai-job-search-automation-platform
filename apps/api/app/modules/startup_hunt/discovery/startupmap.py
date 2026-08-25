"""StartupMap discovery source (PRD sections 9, 39).

Off by default (settings.startup_hunt_startupmap_enabled) pending a ToS/
robots.txt/legal review of StartupMap's actual crawl policy - see the PRD's
own section 39 caveat. The JSON-LD-first extraction below is a best-effort
starting point: many directory sites embed schema.org/Organization data for
SEO, but StartupMap's actual page markup has not been verified against the
live site - do that before ever flipping startup_hunt_startupmap_enabled on
in production, and adjust _extract_organizations if it doesn't match.
"""

from __future__ import annotations

import json
import logging
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

_DISCOVERY_SOURCE = "startupmap"


def is_available() -> bool:
    return settings.startup_hunt_startupmap_enabled and bool(settings.startup_hunt_startupmap_url)


def _extract_organizations(html: str) -> list[dict[str, Any]]:
    """Parses every JSON-LD block on the page and pulls out Organization
    entries, including ones nested inside an ItemList/CollectionPage (the
    common shape for a directory listing page). Best-effort: malformed JSON
    or an unexpected shape is skipped, never raised - one bad block must not
    fail the whole discovery run."""
    organizations: list[dict[str, Any]] = []
    for match in _JSON_LD_PATTERN.finditer(html):
        try:
            data = json.loads(match.group(1).strip())
        except (json.JSONDecodeError, AttributeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            item_type = candidate.get("@type")
            if item_type == "Organization":
                organizations.append(candidate)
            elif item_type in ("ItemList", "CollectionPage"):
                for entry in candidate.get("itemListElement", []) or []:
                    item = entry.get("item") if isinstance(entry, dict) else None
                    if isinstance(item, dict) and item.get("@type") == "Organization":
                        organizations.append(item)
    return organizations


def _to_discovered(org: dict[str, Any]) -> DiscoveredStartup | None:
    name = str(org.get("name") or "").strip()
    if not name:
        return None
    website_url = str(org.get("url") or "").strip() or None
    address = org.get("address") if isinstance(org.get("address"), dict) else {}
    return DiscoveredStartup(
        name=name,
        domain=extract_domain(website_url),
        website_url=website_url,
        country=str(address.get("addressCountry") or "").strip() or None,
        city=str(address.get("addressLocality") or "").strip() or None,
        discovery_source=_DISCOVERY_SOURCE,
        discovery_source_url=settings.startup_hunt_startupmap_url,
        discovery_source_id=str(org.get("@id") or "").strip() or None,
    )


class StartupMapSource:
    name = _DISCOVERY_SOURCE

    async def discover(self) -> list[DiscoveredStartup]:
        if not is_available():
            return []
        try:
            html = await safe_fetch(settings.startup_hunt_startupmap_url)
        except SSRFBlockedError:
            logger.exception("StartupMap discovery fetch blocked by SSRF guard")
            return []
        except Exception:
            logger.exception("StartupMap discovery fetch failed")
            return []

        organizations = _extract_organizations(html)
        discovered = [d for org in organizations if (d := _to_discovered(org)) is not None]
        if not discovered:
            logger.warning(
                "StartupMap discovery found zero Organization entries - the page's markup may not "
                "match this extractor's JSON-LD assumptions; verify against the live site."
            )
        return discovered
