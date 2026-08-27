# Startup Hunt: Low-Level Design (LLD)

**Document Version:** 2.0.0  
**Status:** Approved for Production  

---

## 1. Directory & Code Architecture

```
apps/api/app/modules/startup_hunt/
├── __init__.py
├── engine.py          # Core discovery & resolution orchestrator (173KB)
├── service.py         # Business logic, company/opportunity CRUD & search
├── resolver.py        # Domain-to-ATS mapping engine
├── routes.py          # REST HTTP endpoints
├── models.py          # PostgreSQL models (CompanyRegistry, StartupHuntCompany, etc)
├── schemas.py         # Pydantic request & response validation DTOs
├── tasks.py           # Celery background task registration
├── discovery/         # Directory adapters (StartupMap, Google Web)
├── ingestion/         # Ingestion sub-system
│   ├── ats_resolver.py # ATS heuristic detector (meta tag / header inspection)
│   ├── ssrf_guard.py  # Network safety guard & DNS IP pinning
│   ├── generic_crawler.py # HTML scraping fallback engine
│   ├── job_sync.py    # Database job upsert logic
│   └── backoff.py     # Exponential backoff retry handler
├── providers/         # Specific ATS board parsers
│   ├── greenhouse.py
│   ├── lever.py
│   ├── ashby.py
│   ├── theirstack.py
│   └── google_web.py
└── workers/           # Async state machine background workers
    ├── discovery_worker.py
    ├── resolution_worker.py
    ├── sync_worker.py
    └── backfill_worker.py
```

---

## 2. Low-Level Component Mechanics

### 2.1 SSRF Guard & Security Layer (`ssrf_guard.py`)

To prevent Server-Side Request Forgery when crawling arbitrary user-submitted or discovered career URLs, every outgoing HTTP request is wrapped by `SafeHTTPClient`:

```python
import ipaddress
import socket
from urllib.parse import urlparse

BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"), # AWS Metadata Endpoint
    ipaddress.ip_network("::1/128"),
]

def validate_target_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Disallowed scheme: {parsed.scheme}")
        
    hostname = parsed.hostname
    # Resolve DNS to IPv4/IPv6 address
    ip_addresses = socket.getaddrinfo(hostname, None)
    for res in ip_addresses:
        ip = ipaddress.ip_address(res[4][0])
        for blocked_net in BLOCKED_IP_NETWORKS:
            if ip in blocked_net:
                raise SecurityError(f"SSRF violation: {hostname} resolved to blocked IP {ip}")
    return url
```

---

### 2.2 ATS Heuristic Detection (`ats_resolver.py`)

Identifies target company ATS platforms without requiring predefined configuration:

1. **Host Marker Matching**: Inspects domain against known ATS domains:
   - `boards.greenhouse.io` / `grnh.se` -> Greenhouse
   - `jobs.lever.co` -> Lever
   - `jobs.ashbyhq.com` -> Ashby
   - `*.personio.de` / `jobs.personio.de` -> Personio
   - `*.workable.com` -> Workable
2. **HTML Meta-Tag Inspection**: If host is custom (e.g. `careers.techcorp.com`), fetches home page HTML and checks DOM meta markers:
   - `<meta name="generator" content="Greenhouse">`
   - Script sources matching `cdn.ashbyhq.com` or `lever-jobs-widget`.

---

### 2.3 Async Worker Pipeline (`workers/`)

Workers operate on `company_registry` rows via optimistic locking (`FOR UPDATE SKIP LOCKED`):

#### 1. Discovery Worker (`discovery_worker.py`)
- Reads raw startup domains from `StartupMap` and `Google Web`.
- Inserts new rows into `company_registry` with `status = 'discovered'`.

#### 2. Resolution Worker (`resolution_worker.py`)
- Queries `company_registry WHERE status = 'discovered' LIMIT 50`.
- Executes `ats_resolver.resolve_company(company)`.
- Updates row with `company_careers_url`, `ats_platform`, and transitions status to `'resolved'` or `'no_careers_page'`.

#### 3. Sync Worker (`sync_worker.py`)
- Queries `company_registry WHERE status IN ('resolved', 'active') AND last_crawled_at < NOW() - INTERVAL '24 hours'`.
- Invokes provider parser (`greenhouse.fetch_jobs()`, `lever.fetch_jobs()`, etc.).
- Upserts listings into shared `jobs` table with `origin_tool = 'startup_hunt'`.
- Updates `last_crawled_at` timestamp.

---

### 2.4 Generic Crawler Fallback (`generic_crawler.py`)

When an ATS board is not recognized, `generic_crawler` performs DOM extraction:
1. Searches HTML for anchor tags (`<a>`) matching job keywords: `/job/`, `/careers/`, `/position/`, `/vacancy/`, `apply`.
2. Extracts job title from `<h1>` or `<h2>` headings.
3. Normalizes and validates location text.
4. Tags output as `source = 'generic_crawler'`.
