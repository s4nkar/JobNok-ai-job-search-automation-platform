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
try:
    from ddgs import DDGS  # ddgs >= 9.x (renamed package)
except ImportError:
    from duckduckgo_search import DDGS  # duckduckgo-search < 9.x fallback

from lib.config import settings

log = logging.getLogger(__name__)

APOLLO_PEOPLE_URL = "https://api.apollo.io/v1/mixed_people/search"

CONTACT_TITLE_TARGETS = [
    "Founder", "Co-Founder", "CEO", "CTO",
    "VP Engineering", "Head of Engineering",
    "Senior Software Engineer", "Senior Engineer",
]

_SKIP_URL_FRAGMENTS = [
    "linkedin.com/jobs", "linkedin.com/posts", "linkedin.com/pulse",
    "linkedin.com/company",  # company LinkedIn pages aren't parseable startup profiles
    "indeed.com", "glassdoor.com",
    "angel.co/jobs", "ycombinator.com/jobs", "jobs.lever.co",
    "boards.greenhouse.io", "wellfound.com/jobs",
    "recruitee.com", "greenhouse.io", "lever.co",  # ATS job-posting domains
    "instagram.com", "twitter.com", "x.com", "facebook.com",
    "wikipedia.org",  # encyclopedia pages, not company profile pages
]
# URL path segments that indicate a directory/listing page or news article
_SKIP_URL_SEGMENTS = [
    "/search?", "?q=", "/tag/", "/category/", "/search/",
    "/startups-in-", "/companies-in-", "/explore", "/discover",
    "/funding-stage", "/funding/", "/blog/", "/news/", "/report",
    "/jobs", "/about", "/contact", "/press", "/privacy",
    "/article/", "/articles/", "/story/", "/post/",
    # Crunchbase sub-navigation tabs that are NOT company profiles
    "/signals_and_news", "/recent_investments", "/org_similarity",
    "/similar_companies", "/timeline", "/advisors",
    "/current_team", "/past_team",
    # German directory/listing URL patterns
    "/datenbank", "/datenbank-", "/bericht", "-report-",
    "/analyse", "/analyse-", "/neugründungen", "/woche",
    "/uebersicht", "/liste", "/verzeichnis",
]
_META_DOMAINS = {"duckduckgo.com", "bing.com", "google.com", "yahoo.com", "msn.com"}
# News / media domains — results from these are almost always articles, not company pages
_NEWS_DOMAINS: frozenset[str] = frozenset({
    "techcrunch.com", "eu-startups.com", "sifted.eu", "bloomberg.com",
    "reuters.com", "ft.com", "businessinsider.com", "businessinsider.de",
    "forbes.com", "handelsblatt.com", "gruenderszene.de", "startupvalley.news",
    "t3n.de", "heise.de", "wired.com", "venturebeat.com",
    "manager-magazin.de", "wirtschaftswoche.de", "gründerszene.de",
    "faz.net", "sueddeutsche.de", "spiegel.de", "zeit.de",
    "bild.de", "focus.de", "stern.de",
    # Music / entertainment press
    "musicbusinessworldwide.com", "variety.com", "billboard.com",
    # Investment promotion / government sites (articles, not startup profiles)
    "invest-in.berlin", "gtai.de", "germany.info", "berlin-partner.de",
    "gruendermetropole-berlin.de", "why.berlin",
    # Funding tracker aggregators / revenue analytics
    "vcbacked.com", "tracxn.com", "pitchbook.com", "getlatka.com",
    # Startup list aggregators (articles, not company pages)
    "growthlist.co", "topstartups.io", "tech-now.io",
    # General tech / startup press
    "thenextweb.com", "zdnet.com", "cnet.com", "inc.com",
    "entrepreneur.com", "fastcompany.com", "medium.com",
    "techfundingnews.com", "cybernewscentre.com", "eustartup.news",
    "retailtechinnovationhub.com",
    # Austrian / Central European startup press
    "trendingtopics.eu", "brutkasten.com", "startup-insider.com",
    "majunke.com", "aistartuphub.com", "ecomio.com",
    # Job boards masquerading as startup directories
    "berlinstartupjobs.com", "berlinstartupjobs.de",
    # Berlin community blogs / university pages
    "ai-berlin.com", "startbase.de", "berlin-startups.net",
    "tu.berlin", "htgf.de",  # German uni & fund pages, not startup profiles
    "ai-nation.de",
    # Startup news / funding announcement blogs
    "startuprise.co.uk", "startupblink.com", "startupranking.com",
})
# For known startup-directory domains, only profile-page URL paths are accepted.
# This blocks hub pages, listing pages, search results, etc. from those domains.
_DIRECTORY_PROFILE_PATHS: dict[str, str] = {
    "crunchbase.com": "/organization/",
    "wellfound.com": "/company/",
    "ycombinator.com": "/companies/",
    # f6s.com removed — URL structure varies; pass-through with normal filters
    "dealroom.co": "/companies/",   # app.dealroom.co/companies/NAME — blocks .startups filter pages
    "germanyy.ai": "/startups/",
    "startupdetector.de": "/startup/",
    "antler.co": "/portfolio/",
    "plug-and-play.com": "/portfolio/",
    "seedtable.com": "/companies/",
}
# News article URLs contain a 4-digit year in the path (e.g. /2025/01/12/mirelo-raises-...)
_ARTICLE_URL_RE = re.compile(r"/20\d{2}/\d{2}/")
# Titles that indicate listing/category pages rather than individual company names.
# KEEP THIS LIST NARROW — news articles are already caught by _NEWS_DOMAINS and
# _ARTICLE_URL_RE. Only add patterns that are unambiguously not a company name.
_LISTING_TITLE_RE = re.compile(
    # English listing / directory page patterns (numbered lists, curated lists, etc.)
    r"(\d+[+]?\s+\w[\w\s]*)?(startups?\s+in\b|companies?\s+in\b"
    r"|\bbest\b.{0,30}\b(startups?|companies?)\b"
    r"|\b(top|best)\b.{0,30}\b(startups?|companies?|ai\s+start)"
    r"|\bstartups?\s+to\s+watch\b|\bstartups?\s+hiring\b"
    r"|\b(explore|discover|browse|find)\b.*\bstartup"
    r"|\bstartup.*\blist\b|\blist\s+of\b|\brunking\b)"
    # German listing / directory page patterns
    r"|\bstartups?\s+entdecken\b|\bneue\s+startups?\b|\balle\s+neuen\b"
    r"|\bstartup[- ]datenbank\b|\bdatenbank\b"
    r"|\bwöchentlich\b|\bper\s+loop\b"
    r"|\bneugründung(?:en)?\b|\bfinanzierungsrunden?\b"
    r"|\bstartup[- ]verzeichnis\b|\bstartup[- ]liste\b"
    r"|\bstartups?\s+tracken\b|\bstartups?\s+entdecken\b"
    # Fundraise headline verbs — never in a company profile page title
    r"|\braises?\b"
    # Investor / VC fund page titles
    r"|\bventure\s+capital\b|\bvc\s+fund\b|\binvestment\s+fund\b"
    r"|\bfunding\s*(&|and)\s*investors?\b|\bfunding\s+history\b"
    r"|\binvestors?\s+and\s+funding\b|\bpre[- ]seed\s+investors?\b"
    r"|\bactive\s+investors?\b"
    # Bare generic single-word titles
    r"|^startup$|^startups$|^company$|^companies$|^exclusive$",
    re.I,
)
# Descriptions that reveal a non-startup organisation rather than a product company
_NON_STARTUP_DESC_RE = re.compile(
    # VC / investment funds — broad set of patterns
    r"\b(venture\s+capital\s+fund|venture\s+capital\s+firm|venture\s+capital\s+company"
    r"|vc\s+fund|vc\s+firm|investment\s+fund|investment\s+firm"
    r"|growth\s+(?:equity|capital)\s+firm"
    r"|portfolio\s+of\s+.{0,40}investments?"
    r"|investment\s+returns?|fund\s+manager"
    r"|focuses\s+on\s+(seed|pre[- ]seed|series)\s+.{0,40}investments?"
    r"|invests?\s+in\s+(pre[- ]?seed|seed|early[- ]stage)"  # Java Capital, Atmos
    r"|\bseed\s+fund\b|\bpre[- ]?seed.{0,10}fund\b"          # Breega "Seed Fund"
    r"|investing,?\s+nurturing"                                # Atmos "investing, nurturing"
    r"|early[- ]stage\s+(ai\s+)?invest)"
    # Accelerators / incubators / programs
    r"|\b(acceleration\s+program|accelerator\s+program|incubator\s+program"
    r"|incubation\s+program\b"                                  # KIEZ "An incubation program for..."
    r"|has\s+invested\s+in\b|portfolio\s+companies?\b)"
    # Non-profits / communities / meetups
    r"|\b(not[- ]for[- ]profit|non[- ]for[- ]profit|nonprofit|meetup\.com\s+community"
    r"|links?\s+local\s+groups|fifteen\s+cities|open\s+source\s+initiative"
    r"|non[- ]profit\s+\w{0,20}\s*community"                   # heidelberg.ai
    r"|community\s+of\s+(?:\w+\s+){1,4}specialists?\b"        # AI Guild "community of... specialists"
    r"|promote\s+(?:ai|tech|digital)\s+adoption\b)"             # AI Guild "promote AI adoption"
    # Research institutes / government bodies
    r"|\b(public[- ]private\s+partnership"                     # DFKI PPP
    r"|publicly\s+owned\s+until\s+going\s+public"
    r"|founded\s+in\s+1[5-9]\d{2}\b)"                         # very old companies (pre-2000)
    # Large established corporations
    r"|\b(world'?s\s+oldest\s+(?:operating\s+)?\w+"           # Merck "world's oldest"
    r"|multinational\s+(?:\w+\s+){0,2}(?:company|corporation|group|conglomerate)"
    r"|present\s+in\s+over\s+\d{2,}\s+countries"              # Unify "over 100 countries"
    r"|went\s+public\s+in\s+\d{4}"
    r"|publicly\s+traded\s+on)"
    # VC funds / angel investors — additional patterns not in the base set
    r"|\b(seed\s+stage\s+investor"                             # HTGF "seed stage investor"
    r"|most\s+active.{0,20}seed"                               # "most active seed investor"
    r"|invest\s+at\s+a?\s*(?:\(pre[- ]?\))?seed"              # Food Labs "invest at a (pre-)seed"
    r"|seed\s+stage\s+vc\b"                                    # Faber Ventures
    r"|angel\s+investor\b"                                     # Volders personal page
    r"|we\s+finance\s+your\s+technology)"                      # HTGF "we finance your..."
    # Crunchbase tag/category snippet (not a description at all)
    r"|\bHeadquarters\s+Regions\b"                             # Atmos Ventures tag-list
    # Physical-product manufacturers / distributors (not software/tech)
    r"|\b(manufactures?\s+(?:and\s+)?(?:distributes?|supplies?|sells?)"
    r"|distributor\s+of\s+(?:tabletop|food|household|kitchen|shoe|print)"
    r"|shoe\s+care\s+(?:products?|creams?)"
    r"|cosmetics?\s+and\s+pharmaceuticals?"
    r"|household\s+and\s+kitchen\s+products?"
    r"|industrial\s+machin(?:ery|es?)?"
    r"|air\s+curtain\s+systems?"
    r"|metallized\s+(?:and\s+holographic\s+)?films?"
    r"|coding\s+and\s+printing\s+technolog)"
    # Job boards / staffing / directories
    r"|\b(publish\s+job\s+advertisements?|job\s+advertisements?\s+on"
    r"|online\s+directory\s+listing|listing\s+startups?\s*,\s*investors?"
    r"|provision\s+of\s+programmers)"
    # Crunchbase aggregation page snippets (city/hub list pages indexed by DDG)
    r"|\bNumber\s+of\s+Organizations\b|\bTotal\s+Funding\s+Amount\b"
    r"|\bNumber\s+of\s+Investors\b|\bTop\s+\d+[Kk]\b",
    re.I,
)
# Titles that clearly identify a non-startup (accelerator, academy, fund, etc.)
_NON_STARTUP_TITLE_RE = re.compile(
    r"\b(bootcamp|startup\s+academy|founders?\s+fund\b|innovation\s+agency"
    r"|coworking|maker\s*space|ecosystem\b|incubator\b|accelerator\b"
    r"|startup\s+map\b|startup\s+group\b|startup\s+hub\b"
    r"|research\s+cent(?:er|re)\b"                            # e.g. "Research Center for …"
    r"|cent(?:er|re)\s+for\s+(?:artificial\s+intelligence"   # "Center for Artificial Intelligence"
    r"|machine\s+learning|robotics|data\s+science|autonomous)"
    r"|innovation\s+park\b"                                   # "Innovation Park AI"
    r"|\bforschungszentrum\b"                                 # German "research centre"
    r"|\binstitut(?:e|)\s+f[oü]r\b"                          # "Institute for / Institut für"
    r"|\bartificial\s+intelligence\s+institute\b"             # "China Germany AI Institute"
    r"|\bgründerfonds\b|\bfonds\b"                            # German "Fonds" = fund (HTGF)
    # VC / investment names: title ENDS with these fund-marker words
    r"|\s+(?:capital|ventures?|fund|investors?)\s*$)",        # "TVM Capital", "Alpha Intelligence Capital"
    re.I,
)
# Description patterns that identify non-startups not caught by the title regex
_NON_STARTUP_DESC_EXTRA_RE = re.compile(
    r"\bR&D\s+(?:division|lab|cent(?:er|re))\b"              # "R&D division of Bosch"
    r"|\bsubsidiary\s+of\b"                                   # acquired/subsidiary
    r"|\bowned\s+by\s+\w"                                     # "owned by Atos"
    r"|\bdivision\s+of\s+[A-Z]",                             # "division of Bosch"
    re.I,
)
# City/country names that should never be mistaken for a company name
_GEO_NAMES: frozenset[str] = frozenset({
    "berlin", "london", "munich", "münchen", "paris", "amsterdam", "hamburg",
    "frankfurt", "cologne", "köln", "düsseldorf", "stockholm", "vienna", "wien",
    "zurich", "zürich", "madrid", "barcelona", "lisbon", "dublin", "warsaw",
    "brussels", "singapore", "new york", "san francisco", "boston", "seattle",
    "austin", "germany", "france", "uk", "europe", "us", "usa", "india",
})

MAX_PLATFORMS = 8  # kept for _select_platforms (used by future features); not used in search_startups


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _clean(html_text: str) -> str:
    return " ".join(unescape(_strip_tags(html_text)).split())


def _extract_domain(url: str) -> str | None:
    """Return the apex domain (e.g. lb.crunchbase.com → crunchbase.com)."""
    m = re.search(r"https?://([^/?#]+)", url)
    if not m:
        return None
    host = m.group(1).lower().split(":")[0]  # strip port
    parts = host.split(".")
    # Handle 2-part SLDs (co.uk, co.jp, com.br …) → keep 3 labels
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "gov"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


# ── DDG search via duckduckgo-search library ──────────────────────────────────
# The library (pip: duckduckgo-search) handles retries, endpoint rotation and
# back-off automatically — far more reliable than the raw HTML endpoint.

async def _ddg_search(query: str, max_results: int = 15) -> list[dict[str, str]]:
    """Search DuckDuckGo and return list of {href, title, body} dicts."""
    try:
        raw = await asyncio.to_thread(
            lambda: list(DDGS().text(query, max_results=max_results))
        )
    except Exception as exc:
        log.warning("DDG search failed for %r: %s: %s", query[:80], type(exc).__name__, exc)
        return []

    results: list[dict[str, str]] = []
    for r in raw:
        href = r.get("href") or r.get("url") or ""
        title = (r.get("title") or "").strip()
        body = (r.get("body") or "").strip()
        if href and title:
            results.append({"href": href, "title": title, "body": body})

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
        site_path="startup",   # startupdetector.de/startup/NAME — individual company profiles
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
    # ── Global / broad ───────────────────────────────────────────────────────────
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
        domain="tracxn.com",
        location_keywords=[],  # global fallback
        stages=[], priority=8,
        site_path="d/companies",  # tracxn.com/d/companies/NAME — individual profiles
        query_tpl="{industry} startup {location} {stage}",
        label="Tracxn",
    ),
    Platform(
        domain="craft.co",
        location_keywords=[],  # global fallback
        stages=[], priority=9,
        query_tpl="{industry} startup {location} {stage}",
        label="Craft.co",
    ),
    Platform(
        domain="startupmap.city",
        location_keywords=["berlin", "munich", "münchen", "hamburg", "frankfurt",
                           "london", "paris", "amsterdam", "stockholm", "vienna",
                           "zurich", "zürich", "barcelona", "madrid", "lisbon",
                           "warsaw", "dublin", "brussels", "europe"],
        stages=[], priority=3,
        query_tpl="{location} {industry} startup {stage}",
        label="Startup Map",
    ),
    Platform(
        domain="founded.de",
        location_keywords=["germany", "berlin", "munich", "münchen", "hamburg",
                           "frankfurt", "cologne", "köln", "düsseldorf", "dach",
                           "austria", "switzerland"],
        stages=[], priority=2,
        query_tpl="{industry} startup {location}",
        label="Founded.de",
    ),
    Platform(
        domain="startups.de",
        location_keywords=["germany", "berlin", "munich", "münchen", "hamburg",
                           "frankfurt", "cologne", "köln", "düsseldorf", "dach"],
        stages=[], priority=3,
        query_tpl="{industry} startup {location}",
        label="Startups.de",
    ),
    Platform(
        domain="hub.berlin",
        location_keywords=["berlin", "germany"],
        stages=[], priority=4,
        query_tpl="{industry} startup member",
        label="Hub Berlin",
    ),
    Platform(
        domain="plug-and-play.com",
        location_keywords=["germany", "berlin", "munich", "münchen", "frankfurt",
                           "europe", "us", "usa", "san francisco", "sf", "global"],
        stages=["pre-seed", "seed", "series-a"], priority=6,
        site_path="portfolio",
        query_tpl="{industry} startup {location}",
        label="Plug and Play",
    ),
    Platform(
        domain="5-to-9.de",
        location_keywords=["germany", "berlin", "munich", "münchen", "hamburg",
                           "frankfurt", "dach"],
        stages=[], priority=3,
        query_tpl="{industry} startup {location}",
        label="5-to-9.de",
    ),
    # ── Asia ─────────────────────────────────────────────────────────────────────
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

# ── Employee-count detector ───────────────────────────────────────────────────
# Crunchbase snippets frequently embed the employee band in the format:
#   "Private Seed Berlin, Germany 11-50 company.ai · AI ..."
_EMPLOYEE_RANGE_RE = re.compile(
    r"\b(1-10|11-50|51-100|101-250|251-500|501-1?000|1[,.]?001-5[,.]?000|5[,.]?001-10[,.]?000)\b"
)


def _detect_employee_range(text: str) -> str:
    """Return first employee-band found in text (e.g. '11-50'), or ''."""
    m = _EMPLOYEE_RANGE_RE.search(text)
    return m.group(1) if m else ""


# ── Stage normaliser (for post-search filtering) ──────────────────────────────
_STAGE_CANONICAL: dict[str, str] = {
    "angel":     "angel",
    "pre-seed":  "pre-seed", "pre seed": "pre-seed",
    "seed":      "seed",
    "series-a":  "series-a", "series a": "series-a",
    "series-b":  "series-b", "series b": "series-b",
    "series-c":  "series-c", "series c": "series-c",
    "series-c+": "series-c", "series c+": "series-c",
    "series-d":  "series-d", "series d": "series-d",
    "series-e":  "series-e", "series e": "series-e",
}


def _canonical_stage(raw: str) -> str:
    key = re.sub(r"\s+", " ", raw.strip().lower())
    return _STAGE_CANONICAL.get(key, key)


_STAGE_RE = re.compile(
    r"\b(pre[- ]seed|seed|series\s+[abc][\+]?|series[- ][abc][\+]?|angel)\b",
    re.I,
)
_STAGE_NORMALISE: dict[str, str] = {
    "pre seed": "Pre-Seed", "pre-seed": "Pre-Seed",
    "seed": "Seed",
    "series a": "Series A", "series-a": "Series A",
    "series b": "Series B", "series-b": "Series B",
    "series c": "Series C", "series-c": "Series C",
    "series c+": "Series C+", "series c +": "Series C+",
    "angel": "Angel",
}


def _detect_funding_stage(text: str) -> str:
    """Extract the first funding-stage mention from a snippet, or return ''."""
    m = _STAGE_RE.search(text)
    if not m:
        return ""
    raw = re.sub(r"\s+", " ", m.group(0).strip().lower())
    return _STAGE_NORMALISE.get(raw, m.group(0).title())


def _parse_company(item: dict[str, str], source_platform: str = "web") -> dict[str, Any] | None:
    url = item.get("href", "")
    if not url or any(d in url for d in _SKIP_URL_FRAGMENTS):
        return None

    domain = _extract_domain(url) or ""
    if any(d in domain for d in _META_DOMAINS):
        return None
    if domain in _NEWS_DOMAINS:
        return None
    if any(seg in url for seg in _SKIP_URL_SEGMENTS):
        return None
    if _ARTICLE_URL_RE.search(url):
        return None

    # For known startup directories, require a company-profile URL path.
    req_path = _DIRECTORY_PROFILE_PATHS.get(domain)
    if req_path and req_path not in url:
        return None

    # Crunchbase: enforce strict /organization/SLUG URL — no sub-pages.
    # This blocks /recent_investments, /signals_and_news/timeline, /org_similarity_overview etc.
    if domain == "crunchbase.com":
        if not re.match(r"https?://[^/]+/organization/[^/?#]+/?$", url):
            return None

    # Dealroom: enforce strict /companies/SLUG URL — blocks /companies/f/... filter pages.
    if domain == "dealroom.co":
        if not re.match(r"https?://[^/]+/companies/[^/?#/]+/?$", url):
            return None

    # Block sub-pages of a company profile (tabs: news, team, jobs, etc.)
    url_path = url.split("?")[0].rstrip("/")
    _PROFILE_SUBPAGE_ENDINGS = (
        "/news", "/team", "/jobs", "/funding", "/founders",
        "/about", "/press", "/contact", "/investors",
        "/people", "/profiles", "/profile",
    )
    if any(url_path.endswith(e) for e in _PROFILE_SUBPAGE_ENDINGS):
        return None
    if "/profiles_" in url_path:
        return None

    title = item.get("title", "").strip()
    body  = item.get("body",  "").strip()
    if not title or len(title) < 3:
        return None

    # Reject "Link to <url>" — DDG sometimes uses the href as title for Dealroom
    if re.match(r"^link\s+to\s+", title, re.I):
        return None

    # Reject directory/listing pages, article headlines, VC/fund titles
    if _LISTING_TITLE_RE.search(title):
        return None

    # ── Extract metadata from RAW snippet BEFORE any cleaning ────────────────
    # Crunchbase snippets embed stage and employee-band in context-rich sections
    # (e.g. "Lists Featuring This Company … Germany Seed Stage Companies With
    # Fewer Than 100 Employees") that we are about to strip. Capturing here ensures
    # we don't lose that signal.
    raw_stage = _detect_funding_stage(body)
    raw_size  = _detect_employee_range(body)

    # ── Strip Wellfound generic "careers" boilerplate — contains no company info ─
    body = re.sub(
        r"^Find out if .{1,120} is the right fit for your future career!.*$",
        "", body, flags=re.I | re.DOTALL,
    ).strip()

    # ── Strip noise from description BEFORE any content-based filtering ────────

    # 1. Strip Crunchbase FAQ boilerplate — two variants:
    #    a) starts with "Frequently Asked Questions Where is X's headquarters?…"
    #    b) starts directly with "Where is X's headquarters?…" (header-less variant)
    body = re.sub(r"\s*Frequently Asked Questions\b.*$", "", body, flags=re.I | re.DOTALL).strip()
    body = re.sub(r"\s*Where is [^?]{1,80}(?:'s|s')?\s*headquarters\?.*$", "", body, flags=re.I | re.DOTALL).strip()

    # 2. Strip Crunchbase AI-disclaimer noise
    body = re.sub(
        r"\s*\.\.\.\s*AI Content may contain mistakes[^.]*\.",
        "", body, flags=re.I,
    ).strip()

    # 3. Strip "Lists Featuring This Company. Germany Seed Stage Companies…"
    #    — Crunchbase sidebar/related-lists text indexed by DDG instead of the desc.
    body = re.sub(r"\s*Lists Featuring This Company\b.*$", "", body, flags=re.I | re.DOTALL).strip()

    # 4. Strip Crunchbase metadata header.
    #
    # DDG often indexes the Crunchbase company-card metadata block as the snippet
    # instead of the actual description text.  The block looks like one of:
    #
    #   "Founded. Private Seed Berlin, Germany 1-10 mixedbread.com · AI · Search"
    #   "Founded obfuscation Private Seed Berlin, Berlin, Germany 1-10 site.com"
    #   "Heat Score 58 CompanyName is … Private Berlin, Germany site.com AI ML NLP"
    #
    # Strategy:
    #   a) Strip a leading "Heat Score N" token (keep the rest — may contain desc).
    #   b) Strip the full metadata header when it starts the body (no real desc before it).
    #   c) Strip any trailing "Private [Stage] [City] [Band] [site] · [tags]" suffix
    #      that follows the real description.
    #   d) Convert " · " Crunchbase category separators to ", " for readability.

    # a) Strip "Heat Score N " prefix
    body = re.sub(r"^\s*Heat\s+Score\s+\d+\s+", "", body, flags=re.I).strip()

    # b) Strip full metadata-header when it leads the snippet.
    #    Pattern: optional "Founded[.] [obfuscation]" then "Private|Public [Stage]
    #             [City], [Country] N-M site.com"
    _CB_HEADER = re.compile(
        r"^(?:Founded\.?\s+(?:obfuscation\.?\s+)?)?"
        r"(?:Private|Public)\s+"
        r"(?:(?:Seed|Pre[- ]?Seed|Angel|Series\s+[A-E][\+]?|"
        r"Corporate\s+Round|Early\s+Stage|Late\s+Stage|Convertible\s+Note|M&A)\s+)?"
        r"(?:[A-Z][a-zA-Z\s,]+\s+)?"          # city / country tokens
        r"(?:1-10|11-50|51-100|51-200|101-250|251-500|501-1[,.]?000"
        r"|1[,.]?001-5[,.]?000|5[,.]?001-10[,.]?000)\s+"
        r"\S+",                                 # website token
        re.I,
    )
    body = _CB_HEADER.sub("", body).strip()

    # c) Strip trailing metadata suffix that follows a real description sentence.
    #    E.g. "…intelligent virtual assistants Private Berlin, Germany site.com AI ML"
    body = re.sub(
        r"\s+(?:Private|Public)\s+(?:(?:Seed|Pre[- ]?Seed|Angel|Series\s+[A-E][\+]?|"
        r"Corporate\s+Round|Early\s+Stage|Late\s+Stage)\s+)?"
        r"(?:[A-Z][a-zA-Z\s,]+\s+)?"
        r"(?:1-10|11-50|51-100|51-200|101-250|251-500|501-1[,.]?000"
        r"|1[,.]?001-5[,.]?000)\s+\S+.*$",
        "", body, flags=re.I | re.DOTALL,
    ).strip()

    # d) Strip any remaining "obfuscation" tokens
    body = re.sub(r"\bobfuscated\b\.?\s*\bobfuscation\b\.?", "", body, flags=re.I).strip()
    body = re.sub(r"\bobfuscation\b\.?", "", body, flags=re.I).strip()

    # e) Convert Crunchbase category separators into readable commas
    body = body.replace(" · ", ", ").replace(" • ", ", ")

    # 5. Strip Crunchbase raw metadata artifacts that sometimes leak into snippets
    body = re.sub(r"\s*Contact Email\b.*$", "", body, flags=re.I | re.DOTALL).strip()
    body = re.sub(r"\s*Last funding round type\b.*$", "", body, flags=re.I | re.DOTALL).strip()

    body = re.sub(r"\s{2,}", " ", body).strip()  # collapse leftover whitespace

    # 6. Reject permanently closed companies
    if re.search(r"\bpermanently\s+closed\b", body, re.I):
        return None

    # ── Title → name extraction ────────────────────────────────────────────────

    # Strip directory / job-board suffixes that appear after a separator
    title = re.sub(
        r"\s*[\|–\-]\s*(crunchbase|wellfound|dealroom|f6s|angel\.co|careers?|jobs?).*$",
        "", title, flags=re.I,
    ).strip()
    # Strip bare "Careers" / "Jobs" suffix with NO separator (Wellfound page titles)
    title = re.sub(r"\s+(?:careers?|jobs?|hiring)\s*$", "", title, flags=re.I).strip() or title
    name  = re.split(r"\s*[-–|:]\s*", title, maxsplit=1)[0].strip() or title
    # Belt-and-suspenders: also strip from the extracted name (handles unusual formats)
    name  = re.sub(r"\s+(?:careers?|jobs?|hiring)\s*$", "", name, flags=re.I).strip() or name

    # Reject generic single-word non-names
    if len(name.split()) == 1 and name.lower() in {
        "startup", "startups", "company", "companies", "tech", "fintech",
        "saas", "ai", "news", "blog", "datenbank", "liste", "exclusive",
    }:
        return None

    # Reject bare city/country names
    if name.lower() in _GEO_NAMES:
        return None

    # Reject names that are bare URLs
    if re.match(r"[\w.-]+\.\w{2,}/", name):
        return None

    # Reject names that are comma-separated tag lists (DDG sometimes indexes Crunchbase
    # tag clouds as the page title, e.g. "Artificial Intelligence, Deep Learning, Computer Vision")
    if "," in name:
        return None

    # ── Organisation-type filters ──────────────────────────────────────────────

    if _NON_STARTUP_TITLE_RE.search(title):
        return None
    if body and _NON_STARTUP_DESC_RE.search(body):
        return None
    if body and _NON_STARTUP_DESC_EXTRA_RE.search(body):
        return None

    return {
        "name": name[:200],
        "description": body[:500],
        "website": url,
        "domain": domain,
        "source": source_platform,
        # Pre-extracted from raw snippet before stripping — used by _ingest.
        # Prefixed with _ so they are never serialised to the API response.
        "_raw_stage": raw_stage,
        "_raw_size":  raw_size,
    }


async def search_startups(
    location: str,
    funding_stages: list[str],
    industry: str = "",
    size_range: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Phase A — discover startups via targeted DDG site: queries.

    Only queries large directories that DDG reliably indexes (Crunchbase, Dealroom,
    Wellfound, YC).  Multiple query variants per directory maximise yield.
    3-second gaps between queries keeps us under DDG's soft rate limit.

    Returns a dict with keys:
        companies  — list of company dicts
        meta       — citation / stats dict for the frontend summary card
    """
    limit = max(10, min(limit, 200))  # clamp: 10–200
    # Use up to 3 stages in the query string; DDG handles "OR" well up to 3 terms
    stage_label = " OR ".join(funding_stages[:3]) if funding_stages else ""
    ind = industry.strip() or "tech"
    loc = location.strip()
    loc_lower = loc.lower()

    is_german = any(kw in loc_lower for kw in [
        "germany", "berlin", "munich", "münchen", "hamburg",
        "frankfurt", "cologne", "köln", "düsseldorf", "dach",
        "austria", "switzerland",
    ])
    is_us = any(kw in loc_lower for kw in [
        "us", "usa", "san francisco", "sf", "new york", "nyc",
        "boston", "seattle", "austin", "los angeles",
    ])
    is_europe = is_german or any(kw in loc_lower for kw in [
        "europe", "london", "paris", "amsterdam", "stockholm",
        "madrid", "barcelona", "lisbon", "dublin", "warsaw",
    ])

    seen: set[str] = set()
    companies: list[dict[str, Any]] = []
    # Track how many companies came from each source label
    source_counts: dict[str, int] = {}
    queries_run: int = 0

    def _ingest(items: list[dict[str, str]], source: str) -> None:
        for item in items:
            c = _parse_company(item, source_platform=source)
            if not c:
                continue
            # Dedup by profile URL first (exact), then by name (cross-directory)
            url_key = c["website"].rstrip("/").lower()
            name_key = c["name"].lower()
            if url_key in seen or name_key in seen:
                continue
            seen.add(url_key)
            seen.add(name_key)
            # Pop pre-extracted metadata (must not appear in the API response).
            raw_stage_pre = c.pop("_raw_stage", "")
            raw_size_pre  = c.pop("_raw_size",  "")

            # funding_stage: prefer what was detected in the raw snippet (before stripping
            # stripped context-rich sections like "Lists Featuring This Company…"); fall
            # back to re-detecting from the cleaned description.
            detected = raw_stage_pre or _detect_funding_stage(c.get("description", ""))
            c["funding_stage"] = detected

            # Stage post-filter: if we detected a stage AND it doesn't match any of the
            # requested stages, skip this company. This prevents Series A/B/C companies
            # from leaking through when the user only wants Seed/Pre-Seed results.
            if detected and funding_stages:
                detected_norm = _canonical_stage(detected)
                requested_norms = {_canonical_stage(s) for s in funding_stages}
                if detected_norm not in requested_norms:
                    log.debug(
                        "Stage post-filter: skipping %r (detected=%r, requested=%s)",
                        c["name"], detected, requested_norms,
                    )
                    continue

            # Auto-detect employee range from the raw snippet.
            # If the user specified a size_range filter, honour that value instead.
            detected_size = (raw_size_pre or _detect_employee_range(c.get("description", ""))) if not size_range else ""
            c["location"] = loc
            c["size_range"] = detected_size or size_range
            companies.append(c)
            source_counts[source] = source_counts.get(source, 0) + 1

    # ── Build query list ──────────────────────────────────────────────────────────
    # Crunchbase is the most reliably indexed directory.
    # IMPORTANT: do NOT quote location/industry — quotes kill DDG Crunchbase results.
    queries: list[tuple[str, str]] = [
        (f'site:crunchbase.com/organization {loc} {ind}', "Crunchbase"),
        (f'site:crunchbase.com/organization {loc} {ind} startup {stage_label}', "Crunchbase"),
        (f'site:crunchbase.com/organization {loc} artificial intelligence', "Crunchbase"),
        (f'site:crunchbase.com/organization {loc} {ind} founded team', "Crunchbase"),
        (f'site:wellfound.com/company {loc} {ind}', "Wellfound"),
        (f'site:dealroom.co/companies {loc} {ind} startup', "Dealroom"),
    ]
    if is_german:
        queries += [
            (f'site:germanyy.ai/startups {ind} {loc}', "Germanyy.ai"),
            (f'site:seedtable.com {loc} {ind} startup', "Seedtable"),
        ]
    if is_us:
        queries += [
            (f'site:ycombinator.com/companies {loc} {ind}', "Y Combinator"),
            (f'site:wellfound.com/company {loc} {ind} {stage_label}', "Wellfound"),
        ]
    if is_europe and not is_german:
        queries += [
            (f'site:seedtable.com {loc} {ind} startup', "Seedtable"),
        ]
    # Extra queries for higher limits — more Crunchbase variants + broader terms
    if limit > 50:
        queries += [
            (f'site:crunchbase.com/organization {loc} {ind} series funding', "Crunchbase"),
            (f'site:crunchbase.com/organization {loc} {ind} saas b2b platform', "Crunchbase"),
            (f'site:crunchbase.com/organization {loc} {ind} machine learning deep learning', "Crunchbase"),
            (f'site:wellfound.com/company {loc} {ind} {stage_label}', "Wellfound"),
        ]
    if is_german and limit > 50:
        queries += [
            (f'site:crunchbase.com/organization {loc} {ind} {stage_label}', "Crunchbase"),
            (f'site:f6s.com/companies {loc} {ind}', "F6S"),
            (f'site:founded.de {ind}', "Founded.de"),
            (f'site:crunchbase.com/organization {loc} {ind} automation robotics', "Crunchbase"),
            (f'site:crunchbase.com/organization {loc} {ind} nlp computer vision', "Crunchbase"),
        ]
    if limit > 100:
        queries += [
            (f'site:crunchbase.com/organization {loc} climate health', "Crunchbase"),
            (f'site:crunchbase.com/organization {loc} marketplace b2b', "Crunchbase"),
            (f'site:crunchbase.com/organization {loc} fintech edtech', "Crunchbase"),
            (f'site:crunchbase.com/organization {loc} deep tech hardware', "Crunchbase"),
            (f'site:crunchbase.com/organization {loc} mobility logistics', "Crunchbase"),
            (f'site:crunchbase.com/organization {loc} data analytics platform', "Crunchbase"),
            (f'site:wellfound.com/company {loc} remote {ind}', "Wellfound"),
            (f'site:wellfound.com/company {loc} engineer developer', "Wellfound"),
        ]

    # Per-query result budget: more results per call at higher limits
    # (DDG typically honours up to 25 before rate-limiting aggressively)
    per_query = 15 if limit <= 50 else (25 if limit <= 100 else 30)

    log.info(
        "search_startups: %d queries (per_query=%d) for location=%r stages=%r industry=%r limit=%d",
        len(queries), per_query, loc, funding_stages, ind, limit,
    )

    for i, (q, label) in enumerate(queries):
        if i > 0:
            await asyncio.sleep(2.0)
        results = await _ddg_search(q, max_results=per_query)
        queries_run += 1
        log.info("  [%s] %r → %d hits", label, q[:70], len(results))
        _ingest(results, label)
        if len(companies) >= limit:
            break

    final = companies[:limit]
    log.info("search_startups: %d companies total", len(final))

    meta = {
        "total": len(final),
        "limit": limit,
        "queries_run": queries_run,
        "sources": source_counts,  # e.g. {"Crunchbase": 25, "Wellfound": 10}
        "location": loc,
        "industry": industry.strip() or None,
        "funding_stages": funding_stages,
    }
    return {"companies": final, "meta": meta}


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
