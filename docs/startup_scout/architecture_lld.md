# Startup Scout: Low-Level Design (LLD)

**Document Version:** 2.0.0  
**Status:** Approved for Production  

---

## 1. Codebase Structure

```
apps/api/app/modules/startup_scout/
├── __init__.py
├── engine.py     # Main scraping, DDG site engine, Apollo API integration (76KB)
├── service.py    # Business logic, DB operations, cache management
├── routes.py     # FastAPI HTTP endpoint handlers
├── models.py     # SQLAlchemy models (StartupScoutCompany, StartupScoutContact)
└── schemas.py    # Pydantic request/response validation schemas
```

---

## 2. Low-Level Component Implementation

### 2.1 Domain Blacklisting & URL Normalization (`engine.py`)

Startup Scout uses static analysis on raw DuckDuckGo URLs to weed out news articles, blog posts, and press releases:

```python
_NEWS_DOMAINS: frozenset[str] = frozenset({
    "techcrunch.com", "eu-startups.com", "sifted.eu", "bloomberg.com",
    "reuters.com", "forbes.com", "handelsblatt.com", "gruenderszene.de",
    "trendingtopics.eu", "brutkasten.com", "medium.com"
})

_SKIP_URL_FRAGMENTS = [
    "linkedin.com/jobs", "indeed.com", "glassdoor.com",
    "angel.co/jobs", "ycombinator.com/jobs", "wikipedia.org"
]

def is_valid_startup_url(url: str) -> bool:
    parsed = urlparse(url)
    domain = parsed.netloc.lower().replace("www.", "")
    
    if domain in _NEWS_DOMAINS or domain in _META_DOMAINS:
        return False
        
    for frag in _SKIP_URL_FRAGMENTS:
        if frag in url.lower():
            return False
            
    for seg in _SKIP_URL_SEGMENTS:
        if seg in parsed.path.lower():
            return False
            
    return True
```

---

### 2.2 DDG HTML Rate-Limit Resiliency

DuckDuckGo HTML requests (`html.duckduckgo.com/html`) can emit HTTP `202 Accepted` or `429 Too Many Requests` when queried at high frequency. `engine.py` handles this gracefully:

```python
async def fetch_ddg_html(query: str, client: httpx.AsyncClient) -> str:
    try:
        resp = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=10.0
        )
        if resp.status_code == 202:
            log.warning("DuckDuckGo returned 202 rate-limit response. Skipping query.")
            return ""
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        log.error(f"DDG fetch failed for query '{query}': {exc}")
        return ""
```

---

### 2.3 Apollo Contact Search Fallback (`apollo_search_contacts`)

When web search snippets fail to yield direct founder emails, the engine invokes Apollo's API:

```python
async def apollo_search_contacts(domain: str, titles: list[str]) -> list[dict]:
    if not settings.apollo_api_key:
        return []
        
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": settings.apollo_api_key
    }
    payload = {
        "q_organization_domains": domain,
        "person_titles": titles,
        "page": 1,
        "per_page": 5
    }
    
    async with httpx.AsyncClient() as client:
        res = await client.post(APOLLO_PEOPLE_URL, json=payload, headers=headers, timeout=10.0)
        if res.status_code != 200:
            return []
        data = res.json()
        return data.get("people", [])
```
