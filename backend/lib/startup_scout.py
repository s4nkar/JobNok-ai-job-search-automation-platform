"""Startup Scout — company discovery + contact enrichment.

Phase A: search_startups()        — DDG HTML site: searches against curated startup
                                    directories chosen by location + stage.
Phase B: web_search_contacts()    — DDG search for founder/CEO names extracted
                                    from snippets + LinkedIn profile titles.
         apollo_search_contacts() — Apollo People Search API fallback.

Uses html.duckduckgo.com/html — static HTML endpoint designed for non-JS clients.
If DDG rate-limits (202), the per-query call returns [] and is skipped gracefully.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from html import unescape
from typing import Any

import httpx

from lib.config import settings

log = logging.getLogger(__name__)

APOLLO_PEOPLE_URL = "https://api.apollo.io/v1/mixed_people/search"

CONTACT_TITLE_TARGETS = [
    "Founder", "Co-Founder", "CEO", "CTO",
    "VP Engineering", "Head of Engineering",
    "Senior Software Engineer", "Senior Engineer",
]

_SKIP_URL_FRAGMENTS = [
    "linkedin.com/jobs", "indeed.com", "glassdoor.com",
    "angel.co/jobs", "ycombinator.com/jobs", "jobs.lever.co",
    "boards.greenhouse.io", "wellfound.com/jobs",
]
# URL path segments that indicate a directory/listing page or news article
_SKIP_URL_SEGMENTS = [
    "/search?", "?q=", "/tag/", "/category/", "/search/",
    "/startups-in-", "/companies-in-", "/explore", "/discover",
    "/funding-stage", "/funding/", "/blog/", "/news/", "/report",
    "/jobs", "/about", "/contact", "/press", "/privacy",
    "/article/", "/story/", "/post/",
]
_META_DOMAINS = {"duckduckgo.com", "bing.com", "google.com", "yahoo.com", "msn.com"}
# News article URLs contain a 4-digit year in the path (e.g. /2025/01/12/mirelo-raises-...)
_ARTICLE_URL_RE = re.compile(r"/20\d{2}/\d{2}/")
# Titles that indicate listing/category pages rather than individual company names
_LISTING_TITLE_RE = re.compile(
    r"(\d+\s+\w+\s+)?(startups?\s+in\b|companies?\s+in\b"
    r"|\bbest\b.*\bstartups?\b|\bstartups?\s+to\s+watch\b"
    r"|\b(explore|discover|browse|find)\b.*\bstartup"
    r"|\bstartup.*\blist\b|\bnews\b|\bbreaking\b)",
    re.I,
)

_DDG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
        "Gecko/20100101 Firefox/124.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    # kl=wt-wt = worldwide, no regional bias; no JS required
    "Cookie": "kl=wt-wt",
}

MAX_PLATFORMS = 3  # cap sequential search calls


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _clean(html_text: str) -> str:
    return " ".join(unescape(_strip_tags(html_text)).split())


def _extract_domain(url: str) -> str | None:
    m = re.search(r"https?://(?:www\.)?([^/?#]+)", url)
    return m.group(1).lower() if m else None


# ── Bing search ───────────────────────────────────────────────────────────────

# DDG HTML static-endpoint result patterns
# html.duckduckgo.com/html serves non-JS HTML with class="result__a" anchors
_DDG_RESULT_RE = re.compile(
    r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.I | re.S,
)
_DDG_SNIPPET_RE = re.compile(
    r'class="result__snippet"[^>]*>(.*?)</a>',
    re.I | re.S,
)


async def _ddg_search(query: str, max_results: int = 15) -> list[dict[str, str]]:
    """Search DuckDuckGo HTML endpoint and return list of {href, title, body} dicts."""
    params = {"q": query, "kl": "wt-wt"}
    try:
        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=True, headers=_DDG_HEADERS
        ) as client:
            resp = await client.get("https://html.duckduckgo.com/html/", params=params)
    except Exception as exc:
        log.warning("DDG search failed for %r: %s: %s", query[:80], type(exc).__name__, exc)
        return []

    if resp.status_code == 202:
        log.warning("DDG rate-limited (202) for %r — skipping this query", query[:60])
        return []

    if resp.status_code != 200:
        log.warning("DDG unexpected status %d for %r", resp.status_code, query[:60])
        return []

    urls_titles = _DDG_RESULT_RE.findall(resp.text)
    snippets = [_clean(s) for s in _DDG_SNIPPET_RE.findall(resp.text)]

    results: list[dict[str, str]] = []
    for i, (href, title_html) in enumerate(urls_titles):
        title = _clean(title_html)
        body = snippets[i] if i < len(snippets) else ""
        if href and title and not href.startswith("javascript"):
            results.append({"href": href, "title": title, "body": body})
        if len(results) >= max_results:
            break

    log.debug("DDG: %d results for %r", len(results), query[:60])
    return results


# ── Platform registry ─────────────────────────────────────────────────────────

@dataclass
class Platform:
    domain: str
    location_keywords: list[str]
    stages: list[str]
    query_tpl: str
    priority: int = 99
    label: str = ""
    # Restrict site: search to this path prefix (targets profile pages, not listing pages)
    site_path: str = ""

    def query(self, location: str, industry: str, stage: str) -> str:
        q = self.query_tpl.format(
            location=location,
            industry=industry or "startup",
            stage=stage or "startup",
        )
        site_spec = f"site:{self.domain}/{self.site_path}" if self.site_path else f"site:{self.domain}"
        return f"{site_spec} {q}"


PLATFORMS: list[Platform] = [
    Platform(
        domain="germanyy.ai",
        location_keywords=["germany", "berlin", "munich", "münchen", "hamburg",
                           "frankfurt", "cologne", "köln", "düsseldorf", "dach",
                           "austria", "switzerland"],
        stages=[], priority=1,
        site_path="startups",  # germanyy.ai/startups/NAME — individual company profiles
        query_tpl="{industry} {stage} startup {location}",
        label="Germanyy.ai",
    ),
    Platform(
        domain="startupdetector.de",
        location_keywords=["germany", "berlin", "munich", "münchen", "hamburg",
                           "frankfurt", "cologne", "köln", "düsseldorf"],
        stages=[], priority=2,
        query_tpl="{industry} startup {location}",
        label="Startupdetector",
    ),
    Platform(
        domain="seedtable.com",
        location_keywords=["europe", "germany", "berlin", "munich", "london",
                           "paris", "amsterdam", "stockholm", "madrid", "barcelona",
                           "lisbon", "warsaw", "zurich", "vienna", "uk", "france",
                           "netherlands", "spain", "portugal", "sweden"],
        stages=["seed", "series-a", "series-b"], priority=3,
        query_tpl="{industry} startup {location} {stage}",
        label="Seedtable",
    ),
    Platform(
        domain="dealroom.co",
        location_keywords=["europe", "germany", "berlin", "munich", "london",
                           "paris", "amsterdam", "stockholm", "uk", "france",
                           "netherlands", "spain", "sweden", "poland", "global"],
        stages=[], priority=4,
        site_path="companies",  # dealroom.co/companies/NAME — individual profiles
        query_tpl="{industry} startup {location} {stage}",
        label="Dealroom",
    ),
    Platform(
        domain="f6s.com",
        location_keywords=["europe", "germany", "berlin", "munich", "london",
                           "paris", "amsterdam", "uk", "france", "global"],
        stages=["pre-seed", "seed", "series-a"], priority=5,
        site_path="companies",  # f6s.com/companies/NAME
        query_tpl="{industry} startup {location} {stage}",
        label="F6S",
    ),
    Platform(
        domain="antler.co",
        location_keywords=["germany", "berlin", "europe", "london", "amsterdam",
                           "stockholm", "uk", "singapore", "global"],
        stages=["pre-seed", "seed"], priority=7,
        site_path="portfolio",  # antler.co/portfolio/NAME — individual portfolio companies
        query_tpl="{industry} startup {location}",
        label="Antler",
    ),
    Platform(
        domain="wellfound.com",
        location_keywords=["us", "usa", "new york", "san francisco", "sf", "nyc",
                           "boston", "seattle", "austin", "los angeles", "global"],
        stages=[], priority=2,
        site_path="company",  # wellfound.com/company/NAME — individual profiles only
        query_tpl="{industry} startup {location} {stage}",
        label="Wellfound",
    ),
    Platform(
        domain="ycombinator.com",
        location_keywords=["us", "usa", "san francisco", "sf", "global"],
        stages=["seed", "series-a"], priority=3,
        site_path="companies",  # ycombinator.com/companies/NAME
        query_tpl="{industry} startup {location}",
        label="Y Combinator",
    ),
    Platform(
        domain="inc42.com",
        location_keywords=["india", "bangalore", "bengaluru", "mumbai", "delhi",
                           "hyderabad", "chennai", "pune"],
        stages=[], priority=1,
        query_tpl="{industry} startup {location} funding",
        label="Inc42",
    ),
    Platform(
        domain="yourstory.com",
        location_keywords=["india", "bangalore", "bengaluru", "mumbai", "delhi",
                           "hyderabad", "chennai", "pune"],
        stages=["pre-seed", "seed"], priority=2,
        query_tpl="{industry} startup {location} founder",
        label="YourStory",
    ),
    Platform(
        domain="techinasia.com",
        location_keywords=["singapore", "indonesia", "jakarta", "vietnam", "ho chi minh",
                           "bangkok", "thailand", "malaysia", "kuala lumpur",
                           "southeast asia", "sea", "asia"],
        stages=[], priority=1,
        query_tpl="{industry} startup {location} funding",
        label="Tech in Asia",
    ),
    # Global fallback — always selected so unsupported regions still get results
    Platform(
        domain="crunchbase.com",
        location_keywords=[],
        stages=[], priority=50,
        site_path="organization",  # crunchbase.com/organization/NAME — company profiles
        query_tpl="{industry} startup {location} {stage}",
        label="Crunchbase",
    ),
]


def _select_platforms(location: str, stages: list[str]) -> list[Platform]:
    loc_lower = location.lower()
    selected = [
        p for p in PLATFORMS
        if (not p.location_keywords or any(kw in loc_lower for kw in p.location_keywords))
        and (not p.stages or not stages or any(s in p.stages for s in stages))
    ]
    selected.sort(key=lambda p: p.priority)
    return selected[:MAX_PLATFORMS]


# ── Phase A: company discovery ────────────────────────────────────────────────

def _parse_company(item: dict[str, str], source_platform: str = "web") -> dict[str, Any] | None:
    url = item.get("href", "")
    if not url or any(d in url for d in _SKIP_URL_FRAGMENTS):
        return None

    domain = _extract_domain(url) or ""
    if any(d in domain for d in _META_DOMAINS):
        return None
    if any(seg in url for seg in _SKIP_URL_SEGMENTS):
        return None
    if _ARTICLE_URL_RE.search(url):
        return None

    title = item.get("title", "").strip()
    body = item.get("body", "").strip()
    if not title or len(title) < 3:
        return None

    # Reject directory/listing pages and article titles
    if _LISTING_TITLE_RE.search(title):
        return None

    name = re.split(r"\s*[-–|:]\s*", title, maxsplit=1)[0].strip() or title

    return {
        "name": name[:200],
        "description": body[:500],
        "website": url,
        "domain": domain,
        "source": source_platform,
    }


async def search_startups(
    location: str,
    funding_stages: list[str],
    industry: str = "",
    size_range: str = "",
) -> list[dict[str, Any]]:
    """Phase A — discover startups via sequential Bing site: searches."""
    # Use all selected stages in the query label so the Bing query isn't generic
    stage_label = " OR ".join(funding_stages[:2]) if funding_stages else ""
    platforms = _select_platforms(location, funding_stages)

    log.info(
        "search_startups: %d platforms for location=%r stages=%r — %s",
        len(platforms), location, funding_stages,
        ", ".join(p.label or p.domain for p in platforms),
    )

    seen: set[str] = set()
    companies: list[dict[str, Any]] = []

    def _ingest(items: list[dict[str, str]], source: str) -> None:
        for item in items:
            c = _parse_company(item, source_platform=source)
            if not c:
                continue
            key = c["domain"] or c["name"].lower()
            if key in seen:
                continue
            seen.add(key)
            c["funding_stage"] = ", ".join(funding_stages) if funding_stages else stage_label
            c["location"] = location
            c["size_range"] = size_range
            companies.append(c)

    # Sequential with gap — avoids Bing soft rate limits
    for i, platform in enumerate(platforms):
        if i > 0:
            await asyncio.sleep(1.0)
        query = platform.query(location=location, industry=industry, stage=stage_label)
        results = await _ddg_search(query, max_results=12)
        log.info("  %s → %d hits", platform.label or platform.domain, len(results))
        _ingest(results, platform.label or platform.domain)

    # General fallback if platforms came up empty
    if len(companies) < 5:
        await asyncio.sleep(1.0)
        fallback = f"{industry or 'tech'} startup {location} {stage_label} founders team"
        log.info("search_startups: general fallback query: %r", fallback)
        _ingest(await _ddg_search(fallback, max_results=20), "web")

    log.info("search_startups: %d companies total", len(companies))
    return companies[:40]


# ── Phase B: contact crawl ────────────────────────────────────────────────────

_ROLE_PATTERN = re.compile(
    r"(founder|co-founder|co founder|ceo|cto|chief executive|chief technology"
    r"|vp engineering|head of engineering|president)",
    re.I,
)

_NAME_ROLE_PATTERNS = [
    re.compile(
        r"\b([A-Z][a-z]+ (?:[A-Z][a-z]+ ){0,1}[A-Z][a-z]+)"
        r"[\s,\-–]+(?:is\s+)?(?:the\s+)?(?:a\s+)?"
        r"(founder|co-founder|ceo|cto|chief executive|chief technology"
        r"|vp engineering|head of engineering)",
        re.I,
    ),
    re.compile(
        r"(founder|co-founder|ceo|cto|chief executive|chief technology"
        r"|vp engineering|head of engineering)"
        r"\s+(?:is\s+|and\s+ceo\s+is\s+)?([A-Z][a-z]+ (?:[A-Z][a-z]+ ){0,1}[A-Z][a-z]+)",
        re.I,
    ),
]


def _extract_names_from_snippet(text: str) -> list[dict[str, Any]]:
    contacts = []
    seen_names: set[str] = set()
    for pattern in _NAME_ROLE_PATTERNS:
        for match in pattern.finditer(text):
            g = match.groups()
            if re.search(_ROLE_PATTERN, g[0]):
                role, name = g[0], g[1]
            else:
                name, role = g[0], g[1]
            name = name.strip()
            if name in seen_names or len(name.split()) < 2:
                continue
            seen_names.add(name)
            contacts.append({
                "name": name[:200],
                "title": role.strip().title()[:200],
                "email": None,
                "linkedin_url": None,
                "source": "web_scrape",
                "confidence": 0.5,
            })
    return contacts


def _parse_linkedin_person(item: dict[str, str]) -> dict[str, Any] | None:
    url = item.get("href", "")
    if "linkedin.com/in/" not in url:
        return None
    title = item.get("title") or item.get("body") or ""
    parts = re.split(r" [-–|] ", title, maxsplit=2)
    name = parts[0].strip() if parts else ""
    role = re.sub(r"\s+at\s+.+", "", parts[1], flags=re.I).strip() if len(parts) > 1 else ""
    if not name or len(name) < 2:
        return None
    return {
        "name": name[:200],
        "title": role[:200],
        "email": None,
        "linkedin_url": url,
        "source": "web_scrape",
        "confidence": 0.65,
    }


async def web_search_contacts(company_name: str) -> list[dict[str, Any]]:
    """Phase B step 1 — find founders/CEOs via Bing search."""
    safe_name = company_name.replace('"', "").strip()

    query_general = f'"{safe_name}" founder OR "co-founder" OR CEO OR CTO OR "VP Engineering"'
    query_linkedin = f'"{safe_name}" site:linkedin.com/in founder OR CEO OR CTO OR engineer'

    general_results = await _ddg_search(query_general, max_results=10)
    await asyncio.sleep(1.0)
    linkedin_results = await _ddg_search(query_linkedin, max_results=10)

    contacts: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for item in general_results:
        text = f"{item.get('title', '')} {item.get('body', '')}"
        for c in _extract_names_from_snippet(text):
            if c["name"] not in seen_names:
                seen_names.add(c["name"])
                contacts.append(c)

    for item in linkedin_results:
        c = _parse_linkedin_person(item)
        if c and c["name"] not in seen_names:
            seen_names.add(c["name"])
            contacts.append(c)

    log.info("web_search_contacts: %d contacts for %r", len(contacts), safe_name)
    return contacts


async def apollo_search_contacts(company_name: str) -> list[dict[str, Any]]:
    """Phase B step 2 — Apollo People Search API fallback."""
    if not settings.apollo_api_key:
        return []
    payload = {
        "organization_names": [company_name],
        "titles": CONTACT_TITLE_TARGETS,
        "per_page": 5,
        "page": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                APOLLO_PEOPLE_URL,
                json=payload,
                headers={"Content-Type": "application/json", "x-api-key": settings.apollo_api_key},
            )
            r.raise_for_status()
            people = r.json().get("people", [])
    except Exception as exc:
        log.warning("Apollo people search error: %s", exc)
        return []

    contacts = []
    for p in people:
        email = (p.get("email") or "").strip() or None
        contacts.append({
            "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "title": p.get("title") or "",
            "email": email,
            "linkedin_url": p.get("linkedin_url") or None,
            "source": "apollo",
            "confidence": 0.8 if email else 0.5,
        })
    log.info("apollo_search_contacts: %d contacts for %r", len(contacts), company_name)
    return contacts
