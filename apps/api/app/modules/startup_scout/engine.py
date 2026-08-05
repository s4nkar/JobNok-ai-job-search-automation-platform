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

from app.core.config import settings

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
#
# Design principle: prefer false-negatives (letting a VC through) over
# false-positives (blocking a real startup).  Startups named "Greentech Ventures"
# or "Flagship Capital" must not be silently dropped — the description-level
# filters (_NON_STARTUP_DESC_RE) will catch actual VCs through their text.
_NON_STARTUP_TITLE_RE = re.compile(
    r"\b(bootcamp|startup\s+academy|innovation\s+agency"
    r"|coworking|maker\s*space|ecosystem\b|incubator\b|accelerator\b"
    r"|startup\s+map\b|startup\s+group\b|startup\s+hub\b"
    r"|research\s+cent(?:er|re)\b"                            # "Research Center for …"
    r"|cent(?:er|re)\s+for\s+(?:artificial\s+intelligence"   # "Center for Artificial Intelligence"
    r"|machine\s+learning|robotics|data\s+science|autonomous)"
    r"|innovation\s+park\b"                                   # "Innovation Park AI"
    r"|\bforschungszentrum\b"                                 # German "research centre"
    r"|\binstitut(?:e|)\s+f[oü]r\b"                          # "Institute for / Institut für"
    r"|\bartificial\s+intelligence\s+institute\b"             # "China Germany AI Institute"
    # German fund types — only unambiguous fund-specific compound terms,
    # NOT bare "fonds" which appears in many legitimate German startup names.
    r"|\bgründerfonds\b|\bstaatsfonds\b|\binvestmentfonds\b"
    # Explicit VC/fund phrases that never appear in startup names
    r"|\bfounders?\s+fund\b"                                  # "Founders Fund" (specific VC)
    r"|\bventure\s+capital\s+(?:fund|firm|group|partners?)\b" # "XYZ Venture Capital Fund"
    r"|\bgrowth\s+(?:equity|capital)\s+(?:fund|firm|partners?)\b"
    # Bare acronym + fund-category — blocks "TVM Capital", "HV Ventures", "EQT AB"
    # but NOT "Greentech Ventures" (descriptive prefix) or "Cherry Ventures" (name).
    # Pattern: 1–5 uppercase letters (abbreviation only) followed by fund-type word.
    r"|^[A-Z]{1,5}\s+(?:Capital|Ventures?|Fund|Partners?)\s*$)",
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

# ── API source constants ──────────────────────────────────────────────────────

CRUNCHBASE_API_BASE = "https://api.crunchbase.com/api/v4"

# Crunchbase API v4 funding-stage identifiers → human-readable label.
# Embedded into the synthesised body string so _detect_funding_stage can parse it.
_CB_API_STAGE_MAP: dict[str, str] = {
    "angel":               "Angel",
    "pre_seed":            "Pre-Seed",
    "seed":                "Seed",
    "early_stage_venture": "Series A",   # CB uses this for Series A
    "late_stage_venture":  "Series B",   # CB uses this for Series B+
    "series_a":            "Series A",
    "series_b":            "Series B",
    "series_c":            "Series C",
    "series_d":            "Series D",
    "series_e":            "Series E",
    "ipo":                 "IPO",
}

# Crunchbase num_employees_enum values → human-readable band for _detect_employee_range.
_CB_API_EMPLOYEE_MAP: dict[str, str] = {
    "c_00001_00010": "1-10",
    "c_00011_00050": "11-50",
    "c_00051_00100": "51-100",
    "c_00101_00250": "101-250",
    "c_00251_00500": "251-500",
    "c_00501_01000": "501-1000",
    "c_01001_05000": "1001-5000",
    "c_05001_10000": "5001-10000",
}

# Our funding-stage values → TheirStack API stage identifiers.
_TS_STAGE_MAP: dict[str, str] = {
    "pre-seed": "pre_seed",
    "seed":     "seed",
    "series-a": "series_a",
    "series-b": "series_b",
    "series-c": "series_c",
}

# Location keyword → ISO-2 country codes for TheirStack company_country_code_or filter.
# Keys are lowercase; values are lists so one keyword can expand to multiple countries
# (e.g. "dach" → DE + AT + CH, "europe" → all EU member states).
_LOCATION_TO_COUNTRY_CODES: dict[str, list[str]] = {
    # ── DACH ─────────────────────────────────────────────────────────────────
    "germany": ["DE"],     "deutschland": ["DE"],
    "berlin":  ["DE"],     "munich":      ["DE"],   "münchen":    ["DE"],
    "hamburg": ["DE"],     "frankfurt":   ["DE"],   "cologne":    ["DE"],
    "köln":    ["DE"],     "düsseldorf":  ["DE"],   "stuttgart":  ["DE"],
    "dach":    ["DE", "AT", "CH"],
    "austria": ["AT"],     "vienna":      ["AT"],   "wien":       ["AT"],
    "switzerland": ["CH"], "zurich":      ["CH"],   "zürich":     ["CH"],
    # ── Western Europe ───────────────────────────────────────────────────────
    "france":      ["FR"], "paris":       ["FR"],
    "netherlands": ["NL"], "amsterdam":   ["NL"],
    "belgium":     ["BE"], "brussels":    ["BE"],
    "ireland":     ["IE"], "dublin":      ["IE"],
    # ── Northern Europe ──────────────────────────────────────────────────────
    "sweden":    ["SE"],   "stockholm":   ["SE"],
    "denmark":   ["DK"],   "copenhagen":  ["DK"],
    "finland":   ["FI"],   "helsinki":    ["FI"],
    "norway":    ["NO"],   "oslo":        ["NO"],
    # ── Southern Europe ──────────────────────────────────────────────────────
    "spain":    ["ES"],    "madrid":      ["ES"],   "barcelona":  ["ES"],
    "portugal": ["PT"],    "lisbon":      ["PT"],
    "italy":    ["IT"],    "milan":       ["IT"],   "rome":       ["IT"],
    # ── Eastern Europe ───────────────────────────────────────────────────────
    "poland":  ["PL"],     "warsaw":      ["PL"],   "krakow":     ["PL"],
    "czech":   ["CZ"],     "prague":      ["CZ"],
    # ── UK ───────────────────────────────────────────────────────────────────
    "uk":      ["GB"],  "united kingdom": ["GB"],  "great britain": ["GB"],
    "london":  ["GB"],     "manchester":  ["GB"],   "edinburgh":  ["GB"],
    # ── Europe broad (all major EU + EEA) ────────────────────────────────────
    "europe": ["DE", "FR", "NL", "SE", "PL", "AT", "CH", "ES", "PT",
               "IE", "BE", "DK", "FI", "NO", "IT", "GB", "CZ", "RO"],
    # ── United States ────────────────────────────────────────────────────────
    "us":            ["US"],  "usa":          ["US"],  "united states": ["US"],
    "san francisco": ["US"],  "sf":           ["US"],  "new york":      ["US"],
    "nyc":           ["US"],  "boston":       ["US"],  "seattle":       ["US"],
    "austin":        ["US"],  "los angeles":  ["US"],
    # ── Asia ─────────────────────────────────────────────────────────────────
    "india":     ["IN"],   "bangalore":   ["IN"],   "bengaluru":  ["IN"],
    "mumbai":    ["IN"],   "delhi":       ["IN"],   "hyderabad":  ["IN"],
    "singapore": ["SG"],
}


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


# ── Location → country code helper ───────────────────────────────────────────

def _location_to_country_codes(location: str) -> list[str]:
    """Map a free-text location to ISO-2 country code(s) for TheirStack filtering.

    Tries an exact lowercase match first, then a substring scan (minimum 4-char
    key length to avoid false matches on short abbreviations like "de" or "nl").
    Returns [] for unknown locations so the API call is not filtered by country.
    """
    loc = location.strip().lower()
    if loc in _LOCATION_TO_COUNTRY_CODES:
        return list(_LOCATION_TO_COUNTRY_CODES[loc])
    for key, codes in _LOCATION_TO_COUNTRY_CODES.items():
        if len(key) >= 4 and key in loc:
            return list(codes)
    return []


# ── Crunchbase REST API v4 ────────────────────────────────────────────────────

async def _crunchbase_api_search(
    location: str,
    industry: str,
    funding_stages: list[str],
    limit: int = 25,
) -> list[dict[str, str]]:
    """Search Crunchbase REST API v4 for company profiles.

    Requires CRUNCHBASE_API_KEY (Basic free tier: 200 searches/month).
    Returns results as {href, title, body} dicts — same format as _ddg_search —
    so they feed directly into _parse_company / _ingest without extra plumbing.

    The Crunchbase API is far more reliable than DDG site: queries for EU cities:
    it has full location awareness and structured funding-stage filters.
    """
    if not settings.crunchbase_api_key:
        return []

    # Build free-text search query: "Berlin AI seed startup"
    _STAGE_LABEL: dict[str, str] = {
        "pre-seed": "pre-seed", "seed": "seed",
        "series-a": "series A", "series-b": "series B", "series-c": "series C",
    }
    q_parts = [p for p in [location, industry] if p]
    if funding_stages:
        q_parts.append(" ".join(_STAGE_LABEL.get(s, s) for s in funding_stages[:2]))
    q_parts.append("startup")
    q_text = " ".join(q_parts)

    # Funding-stage predicates (Crunchbase v4 identifiers)
    _STAGE_TO_CB: dict[str, str] = {
        "pre-seed": "pre_seed", "seed": "seed",
        "series-a": "series_a", "series-b": "series_b", "series-c": "series_c",
    }
    cb_stages = [_STAGE_TO_CB[s] for s in funding_stages if s in _STAGE_TO_CB]

    predicates: list[dict] = [
        {"type": "predicate", "field_id": "facet_ids",
         "operator_id": "includes", "values": ["company"]},
    ]
    if cb_stages:
        predicates.append({
            "type": "predicate", "field_id": "funding_stage",
            "operator_id": "includes", "values": cb_stages,
        })

    payload = {
        "field_ids": [
            "identifier", "short_description",
            "location_identifiers", "funding_stage",
            "num_employees_enum", "website_url",
        ],
        "query": predicates,
        "limit": min(limit, 25),  # Crunchbase Basic API max per request
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{CRUNCHBASE_API_BASE}/searches/organizations",
                params={"user_key": settings.crunchbase_api_key, "q": q_text},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log.warning("Crunchbase API error: %s: %s", type(exc).__name__, exc)
        return []

    entities = data.get("entities") or []
    loc_lower = location.strip().lower()
    results: list[dict[str, str]] = []

    for entity in entities:
        props = entity.get("properties") or {}
        identifier = props.get("identifier") or {}
        name = identifier.get("value") or ""
        slug = identifier.get("permalink") or ""
        if not name or not slug:
            continue

        href = f"https://www.crunchbase.com/organization/{slug}"

        # Location post-filter: skip if the API returned a company clearly outside
        # the requested region.  We only filter when the response contains location
        # data AND it clearly doesn't overlap with the user's query.
        loc_ids: list[dict] = props.get("location_identifiers") or []
        loc_text = " ".join(
            (li.get("value") or "") for li in loc_ids if isinstance(li, dict)
        ).lower()
        if loc_text and loc_lower and len(loc_lower) > 3:
            # Accept if any word from user's location appears in CB's location text
            user_words = [w for w in loc_lower.split() if len(w) >= 4]
            if user_words and not any(w in loc_text for w in user_words):
                log.debug("CB API location filter: skipping %r (loc_text=%r)", name, loc_text[:60])
                continue

        # Build body in a format _detect_funding_stage / _detect_employee_range can parse.
        stage_raw   = (props.get("funding_stage") or "").lower()
        stage_human = _CB_API_STAGE_MAP.get(stage_raw, "")
        size_raw    = (props.get("num_employees_enum") or "").lower()
        size_human  = _CB_API_EMPLOYEE_MAP.get(size_raw, "")
        desc        = (props.get("short_description") or "").strip()
        body = " ".join(p for p in [stage_human, loc_text, size_human, desc] if p)

        results.append({"href": href, "title": name, "body": body})

    log.info("Crunchbase API: %d results for q=%r", len(results), q_text[:60])
    return results


# ── TheirStack company search ─────────────────────────────────────────────────

async def _theirstack_company_search(
    location: str,
    funding_stages: list[str],
    industry: str = "",
    limit: int = 25,
) -> list[dict[str, str]]:
    """Search TheirStack company database for EU/global startups.

    Requires THEIRSTACK_API_KEY (already in config from startup_hunt).
    Uses POST /v1/companies/search — separate from the jobs search used by
    startup_hunt.  Filters by country code derived from the location string.

    Returns results as {href, title, body} dicts for _parse_company / _ingest.
    """
    if not settings.theirstack_api_key:
        return []

    country_codes = _location_to_country_codes(location)
    ts_stages     = [_TS_STAGE_MAP[s] for s in funding_stages if s in _TS_STAGE_MAP]

    request_body: dict[str, Any] = {
        "limit": min(limit, 25),
        "page":  0,
        # Prefer companies with recent funding activity
        "order_by": [{"desc": True, "field": "total_funding"}],
        # Cap at 1000 employees — hard startup filter
        "max_employee_count_or_null": 1000,
    }
    if country_codes:
        request_body["company_country_code_or"] = country_codes
    if ts_stages:
        request_body["company_funding_stage_or"] = ts_stages
    if industry:
        # TheirStack supports free-text description pattern matching
        request_body["company_description_pattern_and"] = [industry]

    try:
        base = settings.theirstack_base_url.rstrip("/")
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{base}/v1/companies/search",
                headers={
                    "Authorization": f"Bearer {settings.theirstack_api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log.warning("TheirStack company search error: %s: %s", type(exc).__name__, exc)
        return []

    items = (
        data if isinstance(data, list)
        else data.get("data") or data.get("companies") or data.get("results") or []
    )

    results: list[dict[str, str]] = []
    for item in items:
        name    = (item.get("name") or "").strip()
        website = (item.get("website") or item.get("domain") or "").strip()
        if not name or not website:
            continue
        if not website.startswith("http"):
            website = f"https://{website}"

        # Build body: stage + location + size + description for downstream parsers
        stage_raw   = (item.get("funding_stage") or "").lower()
        stage_human = _CB_API_STAGE_MAP.get(stage_raw, "")

        employees   = int(item.get("number_of_employees") or 0)
        if   employees <=  10: size_human = "1-10"
        elif employees <=  50: size_human = "11-50"
        elif employees <= 100: size_human = "51-100"
        elif employees <= 250: size_human = "101-250"
        elif employees <= 500: size_human = "251-500"
        else:                  size_human = ""

        city    = (item.get("hq_city") or item.get("city") or "").strip()
        country = (item.get("hq_country") or item.get("country") or "").strip()
        loc_str = ", ".join(p for p in [city, country] if p)
        desc    = (
            item.get("short_description")
            or item.get("description")
            or item.get("linkedin_description")
            or ""
        ).strip()

        body = " ".join(p for p in [stage_human, loc_str, size_human, desc[:300]] if p)
        results.append({"href": website, "title": name, "body": body})

    log.info(
        "TheirStack company search: %d results for location=%r stages=%r",
        len(results), location, funding_stages,
    )
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

    # ── Extract metadata from RAW snippet ────────────────────────────────────
    # raw_size: employee-band only appears inside "Lists Featuring This Company"
    # sections which we are about to strip — must be read BEFORE stripping.
    #
    # raw_stage: intentionally deferred until AFTER the "Lists Featuring This
    # Company" strip (step 3 below).  That section contains stage labels for the
    # *list* (e.g. "Germany Series A Companies With Fewer Than 100 Employees"),
    # not for the company itself.  Reading stage before that strip causes valid
    # Seed companies to be mis-classified as Series A and then post-filtered out.
    raw_size = _detect_employee_range(body)
    # raw_stage assigned after step 3 — see below.

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

    # ── Detect funding stage AFTER step 3 ────────────────────────────────────
    # Stage is now detected from the cleaned body (without "Lists Featuring" noise)
    # so that list-section stage labels (e.g. "Germany Series A Companies") don't
    # incorrectly classify a Seed company as Series A and trigger the post-filter.
    raw_stage = _detect_funding_stage(body)

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
    """Phase A — discover startups via structured APIs + targeted DDG site: queries.

    Execution order (EU/Germany-first strategy):
      1. Crunchbase REST API v4  (if CRUNCHBASE_API_KEY set) ─┐ asyncio.gather
      2. TheirStack company API  (if THEIRSTACK_API_KEY set)  ┘ no DDG rate risk
      3. EU-specific DDG queries for germanyy.ai, seedtable.com, startupdetector.de
      4. Global DDG fallback (Crunchbase/Wellfound/Dealroom site: queries)
         — skipped for whichever sources were already covered by APIs above.

    DDG Crunchbase queries are dropped when CRUNCHBASE_API_KEY is set (redundant
    and noisier than the API).  Similarly Wellfound/Dealroom DDG is skipped when
    TheirStack is configured.

    Returns a dict with keys:
        companies  — list of company dicts
        meta       — citation / stats dict for the frontend summary card
    """
    limit = max(10, min(limit, 200))  # clamp: 10–200
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
            # Pop internal metadata fields (must not appear in the API response)
            raw_stage_pre = c.pop("_raw_stage", "")
            raw_size_pre  = c.pop("_raw_size",  "")

            detected = raw_stage_pre or _detect_funding_stage(c.get("description", ""))
            c["funding_stage"] = detected

            # Stage post-filter: if a stage was detected AND it doesn't match any of
            # the requested stages, skip this company.
            if detected and funding_stages:
                detected_norm = _canonical_stage(detected)
                requested_norms = {_canonical_stage(s) for s in funding_stages}
                if detected_norm not in requested_norms:
                    log.debug(
                        "Stage post-filter: skipping %r (detected=%r, requested=%s)",
                        c["name"], detected, requested_norms,
                    )
                    continue

            detected_size = (raw_size_pre or _detect_employee_range(c.get("description", ""))) if not size_range else ""
            c["location"] = loc
            c["size_range"] = detected_size or size_range
            companies.append(c)
            source_counts[source] = source_counts.get(source, 0) + 1

    # ── Phase 1: structured API sources (parallel, no DDG rate-limit risk) ───────
    api_tasks:  list[Any] = []
    api_labels: list[str] = []

    if settings.crunchbase_api_key:
        api_tasks.append(
            _crunchbase_api_search(loc, ind, funding_stages, limit=min(25, limit))
        )
        api_labels.append("Crunchbase API")

    if settings.theirstack_api_key:
        api_tasks.append(
            _theirstack_company_search(loc, funding_stages, ind, limit=min(25, limit))
        )
        api_labels.append("TheirStack")

    if api_tasks:
        raw_api = await asyncio.gather(*api_tasks, return_exceptions=True)
        for raw, label in zip(raw_api, api_labels):
            if isinstance(raw, Exception):
                log.warning("API source %s failed: %s: %s", label, type(raw).__name__, raw)
            else:
                _ingest(raw, label)
                log.info("After %s: %d companies total", label, len(companies))

    # Early exit if APIs alone satisfied the limit
    if len(companies) >= limit:
        final = companies[:limit]
        log.info("search_startups: limit reached from API sources — %d companies", len(final))
        return {
            "companies": final,
            "meta": {
                "total": len(final), "limit": limit, "queries_run": 0,
                "sources": source_counts, "location": loc,
                "industry": industry.strip() or None, "funding_stages": funding_stages,
            },
        }

    # ── Phase 2: DDG site: queries (supplement up to limit) ──────────────────────
    # Skip DDG Crunchbase queries when the Crunchbase API is configured — they are
    # strictly noisier (non-deterministic DDG indexing) than the API results.
    # Skip broad Wellfound/Dealroom DDG when TheirStack covers the same universe.
    use_cb_ddg     = not settings.crunchbase_api_key
    use_broad_ddg  = not settings.theirstack_api_key

    # IMPORTANT: do NOT quote location/industry in Crunchbase DDG queries —
    # quoting kills DDG's Crunchbase site: results (known DDG quirk).
    # For other EU directories (Seedtable, Dealroom) quoting the city name helps
    # DDG understand it as a location filter, not a keyword bag.
    queries: list[tuple[str, str]] = []

    # ── Core global directories ───────────────────────────────────────────────
    if use_cb_ddg:
        queries += [
            (f'site:crunchbase.com/organization {loc} {ind}', "Crunchbase"),
            (f'site:crunchbase.com/organization {loc} {ind} startup {stage_label}', "Crunchbase"),
            (f'site:crunchbase.com/organization {loc} artificial intelligence', "Crunchbase"),
            (f'site:crunchbase.com/organization {loc} {ind} founded team', "Crunchbase"),
        ]
    if use_broad_ddg:
        queries += [
            (f'site:wellfound.com/company {loc} {ind}', "Wellfound"),
            (f'site:dealroom.co/companies {loc} {ind} startup', "Dealroom"),
        ]

    # ── EU / German-specific startup directories ──────────────────────────────
    if is_german:
        queries += [
            (f'site:germanyy.ai/startups {ind} {loc}', "Germanyy.ai"),
            # seedtable.com/companies/NAME is the profile page path — more precise
            (f'site:seedtable.com/companies "{loc}" {ind}', "Seedtable"),
            # startupdetector.de/startup/NAME — individual German startup profiles
            (f'site:startupdetector.de/startup {loc} {ind}', "Startupdetector"),
        ]
    if is_us:
        queries += [
            (f'site:ycombinator.com/companies {loc} {ind}', "Y Combinator"),
            (f'site:wellfound.com/company {loc} {ind} {stage_label}', "Wellfound"),
        ]
    if is_europe and not is_german:
        queries += [
            (f'site:seedtable.com/companies "{loc}" {ind}', "Seedtable"),
            (f'site:dealroom.co/companies "{loc}" {ind} startup', "Dealroom"),
        ]

    # ── Extra queries for higher limits ──────────────────────────────────────
    if limit > 50:
        if use_cb_ddg:
            queries += [
                (f'site:crunchbase.com/organization {loc} {ind} series funding', "Crunchbase"),
                (f'site:crunchbase.com/organization {loc} {ind} saas b2b platform', "Crunchbase"),
                (f'site:crunchbase.com/organization {loc} {ind} machine learning deep learning', "Crunchbase"),
            ]
        if use_broad_ddg:
            queries += [
                (f'site:wellfound.com/company {loc} {ind} {stage_label}', "Wellfound"),
            ]
    if is_german and limit > 50:
        if use_cb_ddg:
            queries += [
                (f'site:crunchbase.com/organization {loc} {ind} {stage_label}', "Crunchbase"),
                (f'site:crunchbase.com/organization {loc} {ind} automation robotics', "Crunchbase"),
                (f'site:crunchbase.com/organization {loc} {ind} nlp computer vision', "Crunchbase"),
            ]
        queries += [
            (f'site:f6s.com/companies {loc} {ind}', "F6S"),
            # Broader germanyy.ai query without city (catches more DE startups)
            (f'site:germanyy.ai/startups {ind}', "Germanyy.ai"),
        ]
    if limit > 100:
        if use_cb_ddg:
            queries += [
                (f'site:crunchbase.com/organization {loc} climate health', "Crunchbase"),
                (f'site:crunchbase.com/organization {loc} marketplace b2b', "Crunchbase"),
                (f'site:crunchbase.com/organization {loc} fintech edtech', "Crunchbase"),
                (f'site:crunchbase.com/organization {loc} deep tech hardware', "Crunchbase"),
                (f'site:crunchbase.com/organization {loc} mobility logistics', "Crunchbase"),
                (f'site:crunchbase.com/organization {loc} data analytics platform', "Crunchbase"),
            ]
        if use_broad_ddg:
            queries += [
                (f'site:wellfound.com/company {loc} remote {ind}', "Wellfound"),
                (f'site:wellfound.com/company {loc} engineer developer', "Wellfound"),
            ]

    per_query = 15 if limit <= 50 else (25 if limit <= 100 else 30)

    log.info(
        "search_startups: %d DDG queries (per_query=%d) for location=%r stages=%r "
        "industry=%r limit=%d [APIs: cb=%s ts=%s → %d companies so far]",
        len(queries), per_query, loc, funding_stages, ind, limit,
        bool(settings.crunchbase_api_key), bool(settings.theirstack_api_key),
        len(companies),
    )

    for i, (q, label) in enumerate(queries):
        if len(companies) >= limit:
            break
        if i > 0:
            await asyncio.sleep(2.0)
        results = await _ddg_search(q, max_results=per_query)
        queries_run += 1
        log.info("  [%s] %r → %d hits", label, q[:70], len(results))
        _ingest(results, label)

    final = companies[:limit]
    log.info("search_startups: %d companies total", len(final))

    meta = {
        "total": len(final),
        "limit": limit,
        "queries_run": queries_run,
        "sources": source_counts,
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

# Name patterns — NOTE: (?-i:...) disables case-insensitivity for the name
# capture group so that [A-Z] only matches uppercase and [a-z] only lowercase.
# Without this, re.I makes [A-Z][a-z]+ match *any* word (e.g. "at", "of", "and"),
# causing sentence fragments to be extracted as fake contacts.
# Each name-word must be at least 3 chars ([A-Z][a-z]{2,} = 3 total minimum).
# This prevents "Co" from "Co-Founder" ever being captured as a surname, while
# still allowing real 3-char names like "Kim", "Lee", "Roy", "Ana", "Max".
_NAME_ROLE_PATTERNS = [
    re.compile(
        r"\b((?-i:[A-Z][a-z]{2,}(?: (?:[A-Z][a-z]{2,})){0,2}))"
        r"[\s,\-–]+(?:is\s+)?(?:the\s+)?(?:a\s+)?"
        r"(founder|co-founder|ceo|cto|chief executive|chief technology"
        r"|vp engineering|head of engineering)",
        re.I,
    ),
    re.compile(
        r"(founder|co-founder|ceo|cto|chief executive|chief technology"
        r"|vp engineering|head of engineering)"
        r"\s+(?:is\s+|and\s+ceo\s+is\s+)?((?-i:[A-Z][a-z]{2,}(?: (?:[A-Z][a-z]{2,})){0,2}))",
        re.I,
    ),
]

# Words that are never part of a real person name — used to reject fragments
_NAME_STOPWORDS: frozenset[str] = frozenset({
    "at", "in", "of", "as", "and", "or", "the", "a", "an", "to", "with",
    "by", "for", "is", "was", "are", "its", "his", "her", "our", "their",
    "we", "he", "she", "they", "it", "this", "that", "from", "on", "into",
    "between", "software", "engineer", "engineering", "technology", "product",
    "design", "lead", "senior", "junior", "based", "via", "roam",
    # Business/funding keywords — never a person's first or last name
    "funding", "venture", "capital", "startup", "series", "angel",
    "growth", "revenue", "acquisition", "merger",
    # Platform/directory names that appear at the start of DDG snippets and
    # get mis-captured as part of a person's name (e.g. "Crunchbase Mauritz Andreae")
    "crunchbase", "linkedin", "wellfound", "angellist", "dealroom",
    "techcrunch", "bloomberg", "reuters", "forbes", "wired",
    # UI labels that appear as snippet prefixes (e.g. "Profile Duncan Blythe")
    "profile", "overview", "about", "bio", "page", "team",
})

# Lowercase name particles that are valid mid-word in European names.
# e.g. "Jan van der Berg", "Florian von Hardenberg", "Pierre de la Rosa"
# These must NOT be treated as uppercase-required words.
_NAME_PARTICLES: frozenset[str] = frozenset({
    "van", "de", "du", "von", "der", "den", "het", "le", "la", "di",
    "da", "dos", "del", "della", "lo", "el", "bin", "binte", "al",
})


def _is_valid_person_name(name: str) -> bool:
    """Return True only if *name* looks like a real person name.

    Rules:
    - 2 to 5 words (allows "Jan van der Berg")
    - First and last word must start with uppercase
    - Middle words may be lowercase particles (van, de, von, …)
    - No word may be a known stopword / generic role word
    - No bare single letter (initials with dot like "J." are allowed)
    """
    words = name.split()
    if not (2 <= len(words) <= 5):
        return False
    # First and last word must start with real uppercase
    if not words[0][0].isupper() or not words[-1][0].isupper():
        return False
    for word in words:
        w = word.lower().rstrip(".")
        # Particles are allowed in middle positions — skip stopword check
        if w in _NAME_PARTICLES:
            continue
        if w in _NAME_STOPWORDS:
            return False
        if len(word) == 1:
            return False
    return True


def _extract_names_from_snippet(text: str, source_url: str = "") -> list[dict[str, Any]]:
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
            if name in seen_names:
                continue
            if not _is_valid_person_name(name):
                continue
            seen_names.add(name)
            contacts.append({
                "name": name[:200],
                "title": role.strip().title()[:200],
                "email": None,
                "linkedin_url": None,
                "source": "web_scrape",
                "source_url": source_url or None,
                "confidence": 0.5,
            })
    return contacts


def _parse_linkedin_person(
    item: dict[str, str],
    company_lower: str = "",
) -> dict[str, Any] | None:
    """Parse a DDG result whose href is a linkedin.com/in/ profile URL.

    LinkedIn page titles follow the pattern:
      "First Last - Role at Company | LinkedIn"

    Two guards against bad results:

    1. Multi-profile concatenation: DDG occasionally fuses several "People also
       viewed" entries into one result. We detect this by splitting on the
       literal string "LinkedIn" where it appears mid-title (i.e. not at the
       end) and keep only the first segment.
       e.g. "Selin K - COO | LinkedInArvind Jain - CEO" → "Selin K - COO"

    2. Relevance: LinkedIn headlines ("Co-Founder at Glean") don't always name
       the target company — but the DDG *body* snippet usually does, because it
       includes a more verbose excerpt of the profile page.  We reject profiles
       whose body doesn't mention the company name.
    """
    url = item.get("href", "")
    if "linkedin.com/in/" not in url:
        return None

    title = item.get("title") or ""
    body  = item.get("body")  or ""

    # Guard 1: strip concatenated multi-profile data.
    # Split on "LinkedIn" followed immediately by an uppercase letter (next name).
    # e.g. "...| LinkedInArvind..." → keep everything before that split point.
    title = re.split(r"LinkedIn(?=[A-Z])", title)[0]
    # Strip the normal trailing "| LinkedIn" suffix
    title = re.sub(r"\s*\|\s*LinkedIn\s*$", "", title, flags=re.I).strip()

    parts    = re.split(r"\s+[-–]\s+", title, maxsplit=1)
    name     = parts[0].strip() if parts else ""
    role_raw = parts[1].strip() if len(parts) > 1 else ""

    # Guard A: role explicitly names a DIFFERENT company.
    # e.g. "Co Founder / CEO of Luna Medical Technology" when searching for LF1.
    # We check role_raw BEFORE stripping so we still have the full "at/of Company" text.
    # LinkedIn headlines always put "at Company" or "of Company" to identify employer.
    if role_raw and company_lower:
        other_co_m = re.search(r'\b(?:at|of)\s+([A-Z][a-zA-Z\s&]{2,40})', role_raw)
        if other_co_m:
            mentioned = other_co_m.group(1).strip().lower()
            # Only reject if the mentioned entity is clearly NOT our target company
            if mentioned and company_lower not in mentioned:
                log.debug(
                    "_parse_linkedin_person: role names different company %r, skipping %s",
                    other_co_m.group(1)[:40], url[:80],
                )
                return None

    # Strip "at Company", "of Company", and "@ Company" suffixes from the role:
    #   "Head of ML at DeepMetis"  →  "Head of ML"
    #   "Co-Founder of Luna Med"   →  "Co-Founder"  (after the guard above already rejected bad ones)
    #   "Head of ML @ DeepMetis"   →  "Head of ML"
    role = re.sub(r"(?:\s+(?:at|of)\s+|\s*@\s*).+$", "", role_raw, flags=re.I).strip()
    # If what's left is just the company name (no actual role info), clear it
    if company_lower and role.lower() == company_lower:
        role = ""

    # Minimal name validation: 2+ words, first word starts uppercase
    name_words = name.split()
    if len(name_words) < 2 or not name_words[0][0].isupper():
        return None
    # Reject if the "name" is actually a job title
    if re.search(r"\b(engineer|developer|manager|director|head|vp|lead|president|officer)\b", name, re.I):
        return None

    # Guard B: title-first relevance check for short company names.
    #
    # For short names (≤4 chars, e.g. "LF1"), the body is unreliable — LinkedIn's
    # own sidebar widgets ("People also at LF1", "Similar profiles at LF1") get
    # indexed by DDG and appear in the body of completely unrelated profiles.
    #
    # The page *title* ("Elliott Spelman - Co-Founder, CEO, Polycam") is always
    # the person's own LinkedIn headline — it's set by the user and reliably
    # identifies their actual employer.  If the company doesn't appear in the title,
    # the person isn't primarily associated with it.
    #
    # For longer names we fall back to the body-only check (title doesn't always
    # repeat the company name for longer names where it's unambiguous in the query).
    if company_lower:
        if len(company_lower) <= 4:
            if not re.search(r'\b' + re.escape(company_lower) + r'\b', title.lower()):
                log.debug(
                    "_parse_linkedin_person: short company %r not in profile title, skipping %s",
                    company_lower, url[:80],
                )
                return None
        elif company_lower not in body.lower():
            log.debug("_parse_linkedin_person: body missing %r, skipping %s", company_lower, url[:80])
            return None

    return {
        "name": name[:200],
        "title": role[:200],
        "email": None,
        "linkedin_url": url,
        "source": "web_scrape",
        "source_url": url,
        "confidence": 0.75,
    }


async def web_search_contacts(company_name: str) -> list[dict[str, Any]]:
    """Phase B step 1 — find founders/CEOs for a specific company via DDG.

    Two queries per company:
      1. General web — looks for name+role mentions in any page
      2. LinkedIn    — looks for linkedin.com/in profiles tied to this company

    Both queries use parenthesised OR so DDG doesn't escape the company-name
    filter (e.g. '"LF1" (founder OR CEO)' vs '"LF1" founder OR CEO' which DDG
    reads as '"LF1" founder' OR 'CEO' — returning random global CEO profiles).

    After fetching, every result is checked for the company name in the snippet
    before any contact is extracted.  This is the primary guard against unrelated
    people leaking into the results (e.g. a LinkedIn CEO profile that happened to
    rank for a short ambiguous company name like "LF1").
    """
    safe_name    = company_name.replace('"', "").strip()
    company_lower = safe_name.lower()

    # Parenthesised OR — keeps role alternatives inside the quoted-name context
    query_general   = f'"{safe_name}" (founder OR "co-founder" OR CEO OR CTO OR "VP Engineering")'
    query_linkedin  = f'site:linkedin.com/in "{safe_name}" (founder OR CEO OR CTO OR engineer)'
    # Crunchbase team pages reliably list founders + titles in the snippet
    query_crunchbase = f'site:crunchbase.com "{safe_name}" founder CEO team'

    general_results   = await _ddg_search(query_general,    max_results=10)
    await asyncio.sleep(1.0)
    linkedin_results  = await _ddg_search(query_linkedin,   max_results=10)
    await asyncio.sleep(1.0)
    crunchbase_results = await _ddg_search(query_crunchbase, max_results=5)

    contacts: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    # ── Snippet relevance check (shared logic) ────────────────────────────────
    # For short company names (≤4 chars) use word-boundary matching to prevent
    # "lf1" from matching inside unrelated technical text or parameter names.
    def _snippet_contains_company(text: str) -> bool:
        t = text.lower()
        if len(company_lower) <= 4:
            return bool(re.search(r'\b' + re.escape(company_lower) + r'\b', t))
        return company_lower in t

    # ── General results ───────────────────────────────────────────────────────
    # The quoted company name is in the query, so DDG should include it in
    # snippets. Reject results where it doesn't appear (catches name collisions
    # for common words — e.g. "here" as a company name).
    for item in general_results:
        text = f"{item.get('title', '')} {item.get('body', '')}"
        if not _snippet_contains_company(text):
            log.debug("web_search_contacts: snippet missing company name, skipping: %s", item.get("href", "")[:80])
            continue
        source_url = item.get("href", "")
        for c in _extract_names_from_snippet(text, source_url=source_url):
            if c["name"] not in seen_names:
                seen_names.add(c["name"])
                contacts.append(c)

    # ── LinkedIn results ──────────────────────────────────────────────────────
    # LinkedIn snippets show the person's headline ("Co-Founder at Acme"),
    # not a page body that repeats the company name — do NOT filter by company
    # name here. The query already scopes results to the company via the quoted
    # name; we trust the query rather than the snippet text.
    for item in linkedin_results:
        c = _parse_linkedin_person(item, company_lower=company_lower)
        if c and c["name"] not in seen_names:
            seen_names.add(c["name"])
            contacts.append(c)

    # ── Crunchbase results ────────────────────────────────────────────────────
    # Crunchbase organization snippets often include founder/CEO names inline.
    # Apply the same company-name filter as general results — Crunchbase
    # snippets reliably contain the company name since we searched for it.
    for item in crunchbase_results:
        text = f"{item.get('title', '')} {item.get('body', '')}"
        if not _snippet_contains_company(text):
            continue
        source_url = item.get("href", "")
        for c in _extract_names_from_snippet(text, source_url=source_url):
            if c["name"] not in seen_names:
                seen_names.add(c["name"])
                contacts.append(c)

    log.info("web_search_contacts: %d relevant contacts for %r", len(contacts), safe_name)
    return contacts


# Domains that are unreliable as professional identity verification sources.
# YouTube videos, Reddit threads, and social media posts sometimes mention a person's
# name alongside a company name, but they don't confirm a professional relationship
# the way LinkedIn, Crunchbase, a company website, or a news article would.
_VERIFY_SKIP_DOMAINS: frozenset[str] = frozenset({
    "youtube.com", "youtu.be",
    "reddit.com", "twitter.com", "x.com",
    "facebook.com", "instagram.com", "tiktok.com",
    "pinterest.com", "tumblr.com", "quora.com",
})


async def verify_contact(
    contact_name: str,
    company_name: str,
    original_source_url: str = "",
) -> tuple[bool, str | None]:
    """Stage 2 — cross-check a contact against an independent professional web source.

    Searches DDG for '"ContactName" "CompanyName"' and returns (is_verified, url)
    where url is the independent page that confirmed the association.

    Rules:
    - Must NOT be the original source URL (prevents a page from verifying itself)
    - Must NOT be from an unreliable domain (YouTube, Reddit, social media)
    - Both name and company must appear in the same snippet
    """
    safe_name    = contact_name.replace('"', "").strip()
    safe_company = company_name.replace('"', "").strip()
    if not safe_name or not safe_company:
        return False, None

    query = f'"{safe_name}" "{safe_company}"'
    try:
        results = await _ddg_search(query, max_results=8)
    except Exception as exc:
        log.warning("verify_contact DDG error for %r/%r: %s", safe_name, safe_company, exc)
        return False, None

    name_lower    = safe_name.lower()
    company_lower = safe_company.lower()

    for r in results:
        url = r.get("href", "")

        # Must be an independent source — skip if it's the same page we found them on
        if original_source_url and url.rstrip("/") == original_source_url.rstrip("/"):
            continue

        # Skip unreliable domains — YouTube videos / Reddit posts are not professional
        # identity verification, even when they mention both name and company
        domain = _extract_domain(url) or ""
        if domain in _VERIFY_SKIP_DOMAINS:
            log.debug("verify_contact: skipping unreliable domain %s for %r", domain, safe_name)
            continue

        # Both name and company must appear in the same snippet
        text = f"{r.get('title', '')} {r.get('body', '')}".lower()
        if name_lower in text and company_lower in text:
            log.debug(
                "verify_contact: confirmed %r at %r via %s",
                safe_name, safe_company, url,
            )
            return True, url

    log.debug("verify_contact: no corroboration for %r at %r", safe_name, safe_company)
    return False, None


def _linkedin_title_matches_name(result_title: str, contact_name: str) -> bool:
    """Return True if the DDG result title plausibly refers to this person.

    LinkedIn page titles look like "First Last - Role at Company | LinkedIn".
    We require that at least the last name (or first name if it's distinctive
    enough — ≥4 chars) appears in the title.  This blocks DDG from returning
    someone else's profile (e.g. Mohamed Belja when we searched Mauritz Andreae).
    """
    title_lower = result_title.lower()
    name_words  = [w for w in contact_name.lower().split() if len(w) >= 3]
    if not name_words:
        return False
    # Last name must match; if first name ≥4 chars, both must match
    last  = name_words[-1]
    first = name_words[0]
    if last not in title_lower:
        return False
    if len(first) >= 4 and first not in title_lower:
        return False
    return True


async def enrich_linkedin_url(contact_name: str, company_name: str) -> str | None:
    """Stage 1.5 — find a LinkedIn profile URL for a contact discovered via web/Crunchbase.

    Contacts scraped from Crunchbase snippets or general web results often have no
    LinkedIn URL because we found them from a text snippet, not a LinkedIn search result.
    This function does a targeted per-person search to fill that gap.

    Two queries tried in order:
      1. '"Name" "Company" site:linkedin.com/in'  — most precise; requires company in snippet
      2. '"Name" site:linkedin.com/in'            — broader fallback for profiles where the
                                                     company name isn't in the DDG-indexed headline

    Both queries validate the result title to ensure the returned profile is actually
    for this person (prevents DDG from returning an unrelated "People also viewed" profile).
    """
    safe_name    = contact_name.replace('"', "").strip()
    safe_company = company_name.replace('"', "").strip()
    if not safe_name:
        return None

    # Query 1: name + company — most targeted
    q1 = f'"{safe_name}" "{safe_company}" site:linkedin.com/in'
    results1 = await _ddg_search(q1, max_results=5)
    for r in results1:
        url   = r.get("href", "")
        title = r.get("title", "")
        if "linkedin.com/in/" not in url:
            continue
        if not _linkedin_title_matches_name(title, safe_name):
            log.debug(
                "enrich_linkedin_url: title mismatch for %r — got %r, skipping",
                safe_name, title[:80],
            )
            continue
        log.debug("enrich_linkedin_url: found %r → %s", safe_name, url[:80])
        return url

    await asyncio.sleep(1.0)

    # Query 2: name only — catches profiles where company name isn't in DDG's indexed headline.
    # Still requires a title match to prevent returning unrelated profiles.
    q2 = f'"{safe_name}" site:linkedin.com/in'
    results2 = await _ddg_search(q2, max_results=5)
    for r in results2:
        url   = r.get("href", "")
        title = r.get("title", "")
        if "linkedin.com/in/" not in url:
            continue
        if not _linkedin_title_matches_name(title, safe_name):
            log.debug(
                "enrich_linkedin_url: fallback title mismatch for %r — got %r, skipping",
                safe_name, title[:80],
            )
            continue
        log.debug("enrich_linkedin_url: fallback found %r → %s", safe_name, url[:80])
        return url

    log.debug("enrich_linkedin_url: no LinkedIn found for %r at %r", safe_name, safe_company)
    return None


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
