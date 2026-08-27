# JobNok — Startup Hunt Automated Discovery & Job Ingestion
## Product Requirements Document (PRD)

**Module:** `startup_hunt`  
**Architecture:** Modular Monolith  
**Status:** Proposed  
**Version:** 1.0  
**Primary markets:** UK, Germany, India, Europe

---

## 1. Executive Summary

This PRD extends the **existing `startup_hunt` module** shown in the current codebase.

The existing module already contains provider integrations for Ashby, Greenhouse, Lever, Google Web, and TheirStack, along with `engine.py`, `resolver.py`, `service.py`, `tasks.py`, models, schemas, and routes.

The goal is **not to replace that architecture**.

Instead, Startup Hunt will be extended with an automated background ingestion pipeline that:

1. Discovers startups from startup directories such as StartupMap.
2. Stores and deduplicates discovered companies.
3. Resolves each company's official careers page.
4. Detects the ATS or job source used by that company.
5. Reuses the existing ATS provider integrations where possible.
6. Fetches jobs from the company's original hiring source.
7. Falls back to generic career-page crawling when structured providers are unavailable.
8. Normalizes and deduplicates jobs into JobNok's central job store.
9. Continuously refreshes jobs using adaptive scheduling.
10. Makes the resulting jobs available to Startup Hunt and the wider Recent Job Search system.

### Core principle

> **Startup directories are discovery sources. The company's own careers page or ATS should be the preferred source for actual job ingestion.**

---

# 2. Current Architecture

The current module is:

```text
modules/
└── startup_hunt/
    ├── providers/
    │   ├── __init__.py
    │   ├── ashby.py
    │   ├── google_web.py
    │   ├── greenhouse.py
    │   ├── lever.py
    │   └── theirstack.py
    │
    ├── __init__.py
    ├── engine.py
    ├── models.py
    ├── resolver.py
    ├── routes.py
    ├── schemas.py
    ├── service.py
    └── tasks.py
```

This architecture should remain the foundation.

The new functionality should be **layered on top of the existing implementation**, not implemented as a separate standalone crawler system.

---

# 3. Target Architecture

The target structure is:

```text
modules/
└── startup_hunt/
    │
    ├── providers/
    │   ├── __init__.py
    │   ├── ashby.py
    │   ├── google_web.py
    │   ├── greenhouse.py
    │   ├── lever.py
    │   └── theirstack.py
    │
    ├── discovery/
    │   ├── __init__.py
    │   ├── startup_source.py
    │   ├── startupmap.py
    │   └── discovery_service.py
    │
    ├── ingestion/
    │   ├── __init__.py
    │   ├── ats_resolver.py
    │   ├── job_sync.py
    │   ├── scheduler.py
    │   └── normalizer.py
    │
    ├── workers/
    │   ├── __init__.py
    │   ├── discovery_worker.py
    │   ├── resolution_worker.py
    │   └── sync_worker.py
    │
    ├── __init__.py
    ├── engine.py
    ├── models.py
    ├── resolver.py
    ├── routes.py
    ├── schemas.py
    ├── service.py
    └── tasks.py
```

### Migration principle

This is a **logical target structure**.

Existing files should be reused and refactored only when necessary.

For example:

- `resolver.py` should continue to own/coordinate source resolution.
- `providers/*.py` should continue to contain provider-specific integrations.
- `service.py` should continue to orchestrate application operations.
- `tasks.py` should continue to integrate background tasks with the application's task system.
- `engine.py` should continue to support the existing Startup Hunt search flow.

Do not duplicate existing provider logic inside the new workers.

---

# 4. Problem

Startup jobs are difficult to discover reliably because early-stage companies often:

- have very small hiring teams;
- use ATS platforms instead of large job boards;
- only publish jobs on their own careers page;
- change their ATS or careers URL;
- are missing from traditional job aggregators;
- create and close positions frequently.

Requiring users to manually enter:

- company name;
- ATS;
- ATS slug;
- careers URL;

creates unnecessary friction.

Startup Hunt should discover and resolve these companies automatically.

---

# 5. Goals

## Primary Goals

1. Automatically discover startups.
2. Support multiple startup discovery sources.
3. Maintain a persistent company registry.
4. Deduplicate companies discovered from multiple sources.
5. Automatically resolve official careers pages.
6. Detect supported ATS platforms.
7. Reuse the existing ATS providers.
8. Add generic career-page crawling as a fallback.
9. Continuously synchronize active jobs.
10. Maintain high job freshness.
11. Deduplicate jobs across all JobNok sources.
12. Keep ingestion asynchronous.
13. Ensure crawler failures do not affect user-facing search.
14. Scale from approximately 5,000 startups to significantly larger datasets.

## Secondary Goals

- Track company hiring activity.
- Prioritize actively hiring startups.
- Track source health.
- Track job freshness.
- Enable future startup watchlists.
- Enable future startup hiring alerts.

---

# 6. Non-Goals

The initial version will not:

- crawl the entire internet;
- mirror third-party job databases;
- use startup directories as the authoritative job source;
- require users to understand ATS platforms;
- crawl every company at the same frequency;
- create a separate job database for Startup Hunt;
- support every ATS immediately;
- introduce microservices.

---

# 7. Core System Flow

```text
Startup Discovery
       │
       ▼
Company Registry
       │
       ▼
Career / ATS Resolution
       │
       ▼
Source Registry
       │
       ▼
Scheduled Job Sync
       │
       ▼
Normalize
       │
       ▼
Deduplicate
       │
       ▼
Central Job Store
       │
       ├───────────────┐
       ▼               ▼
Startup Hunt      Recent Search
```

---

# 8. Three Background Pipelines

Startup Hunt should contain three logically independent background responsibilities.

## 8.1 Pipeline A — Startup Discovery

**Question:**

> What startups should JobNok monitor?

```text
StartupMap / other source
        ↓
Extract startup metadata
        ↓
Normalize
        ↓
Deduplicate
        ↓
Company Registry
```

---

## 8.2 Pipeline B — Company Resolution

**Question:**

> Where does this startup publish its jobs?

```text
Company
   ↓
Company website
   ↓
Careers page
   ↓
ATS detection
   ↓
ATS/source identifier
   ↓
Source Registry
```

Resolution should normally happen once.

It should be repeated only when:

- the source becomes invalid;
- the career page changes;
- the company changes ATS;
- repeated synchronization failures suggest the source is stale.

---

## 8.3 Pipeline C — Job Synchronization

**Question:**

> What jobs does this company currently have?

```text
Known company
      ↓
Known source
      ↓
Fetch jobs
      ↓
Normalize
      ↓
Deduplicate
      ↓
Upsert
```

This is the recurring process.

---

# 9. Startup Discovery

## 9.1 Initial Source

The first discovery source should be **StartupMap**.

The crawler should extract only the information required to identify and resolve a startup.

Preferred fields:

```text
name
domain
website_url
country
city
source
source_url
source_identifier
```

The discovery crawler should not attempt to make StartupMap the primary source of JobNok's job data.

---

# 10. Startup Discovery Abstraction

Startup discovery must be provider-agnostic.

Conceptually:

```python
class StartupSource:
    def discover(self):
        ...
```

Initial implementation:

```text
StartupMapSource
```

Future implementations:

```text
YCSource
EUStartupsSource
AcceleratorSource
StartupDirectorySource
```

Adding another discovery source should not require changes to the core ingestion engine.

---

# 11. Company Registry

Every discovered startup becomes a company record.

Recommended fields:

```text
id
name
normalized_name

domain
website_url

country
city

discovery_source
discovery_source_url
discovery_source_id

career_url

ats_provider
ats_identifier

status

crawl_priority
crawl_frequency

last_discovered_at
last_resolved_at
last_synced_at
next_crawl_at

last_job_found_at
last_job_change_at

consecutive_failures
last_error
```

Exact field names should be aligned with the existing database conventions in `models.py`.

---

# 12. Company Status

Suggested lifecycle:

```text
DISCOVERED
    ↓
RESOLVING
    ↓
RESOLVED
    ↓
ACTIVE
```

Other states:

```text
NO_CAREERS_PAGE
NO_JOBS
FAILED
DISABLED
```

The exact enum implementation should follow existing project conventions.

---

# 13. Company Deduplication

The same company can appear in multiple discovery sources.

Deduplication priority:

1. normalized domain;
2. canonical website;
3. verified company identity;
4. normalized name as a fallback.

Example:

```text
Example AI
example.ai
```

and:

```text
Example AI GmbH
https://www.example.ai
```

should normally resolve to one company.

Domain matching should be preferred over name-only matching.

---

# 14. Career Page Resolution

The existing `resolver.py` should be extended rather than replaced.

Resolution sequence:

```text
Company domain
      ↓
Known career URL?
      │
      ├── Yes → validate
      │
      └── No
           ↓
      Career discovery
           ↓
      ATS detection
           ↓
      Source Registry
```

Potential career paths include:

```text
/careers
/career
/jobs
/join-us
/work-with-us
```

The existing `google_web.py` provider may be reused for career-page discovery where appropriate.

---

# 15. ATS Detection

Initial supported ATS platforms:

```text
Ashby
Greenhouse
Lever
```

Existing integrations:

```text
providers/
├── ashby.py
├── greenhouse.py
└── lever.py
```

should be reused.

Additional providers can be added incrementally.

---

# 16. Provider Architecture

All ATS providers should expose a consistent contract.

Conceptually:

```python
class ATSProvider:

    def resolve(self, company):
        ...

    def fetch_jobs(self, company):
        ...

    def normalize_job(self, raw_job):
        ...
```

Provider-specific logic stays inside:

```text
modules/startup_hunt/providers/
```

Workers should not contain provider-specific scraping/API logic.

---

# 17. Existing Providers

The current providers are:

```text
ashby.py
google_web.py
greenhouse.py
lever.py
theirstack.py
```

They remain part of Startup Hunt.

Their roles:

### `ashby.py`

Ashby resolution and job retrieval.

### `greenhouse.py`

Greenhouse resolution and job retrieval.

### `lever.py`

Lever resolution and job retrieval.

### `google_web.py`

Career/source discovery where appropriate.

### `theirstack.py`

Job aggregation/enrichment/fallback functionality where appropriate.

---

# 18. Ashby Resolution

Example:

```text
https://jobs.ashbyhq.com/company-slug
```

should resolve to:

```text
ats_provider = ashby
ats_identifier = company-slug
```

Once resolved, the system should not repeatedly perform expensive career-page discovery.

Where a structured/public provider interface is available, prefer it over rendering/scraping HTML.

---

# 19. Greenhouse Resolution

Example:

```text
https://boards.greenhouse.io/company
```

should resolve to the Greenhouse provider and relevant board identifier.

Use the existing `greenhouse.py` provider for job retrieval wherever possible.

---

# 20. Lever Resolution

Example:

```text
https://jobs.lever.co/company
```

should resolve to the Lever provider and company/source identifier.

Use the existing `lever.py` provider for job retrieval wherever possible.

---

# 21. Generic Career Crawler

Some startups will not use a supported ATS.

Fallback:

```text
Official careers page
       ↓
Generic crawler
       ↓
Job extraction
       ↓
Normalization
```

Potential extracted fields:

```text
title
location
remote_type
employment_type
department
description
posting_date
application_url
```

The generic crawler is a **fallback**, not the default.

Provider priority should be:

```text
Structured ATS/provider
        ↓
Known ATS page
        ↓
Known career-page pattern
        ↓
Generic crawler
```

---

# 22. Job Synchronization

Once the source is resolved:

```text
company
+
source/provider
+
source_identifier
```

should be sufficient to perform recurring synchronization.

Example:

```text
Example AI
ATS = Ashby
Identifier = example-ai

        ↓

Ashby Sync Worker

        ↓

Current jobs

        ↓

Normalize + Upsert
```

---

# 23. Scheduling Model

Every monitored company should have:

```text
last_synced_at
next_crawl_at
crawl_frequency
crawl_priority
```

The scheduler selects companies where:

```text
next_crawl_at <= current_time
```

and submits them to the synchronization queue.

---

# 24. Adaptive Crawl Frequency

Initial suggested policy:

| Company state | Frequency |
|---|---:|
| New / unresolved | 6–12 hours |
| Actively hiring | 6–12 hours |
| Recently changed | ~12 hours |
| Normal | 24–48 hours |
| No current jobs | ~3 days |
| Dormant | 3–7 days |
| Repeated failures | Exponential backoff |

These values should be configuration-driven and tuned using production metrics.

---

# 25. Crawl Priority

Companies should have a priority score.

### High Priority

Signals:

- recently posted jobs;
- many active positions;
- frequent job changes;
- strong user interest;
- watched by users.

Suggested frequency:

```text
6–12 hours
```

### Normal Priority

```text
24–48 hours
```

### Low Priority

```text
3–7 days
```

---

# 26. Continuous Distribution

Do not execute:

```text
00:00
↓
5,000 companies
```

Instead:

```text
Scheduler
    ↓
Companies due for crawling
    ↓
Small batches
    ↓
Queue
    ↓
Workers continuously process jobs
```

This reduces:

- traffic spikes;
- provider rate-limit risk;
- worker spikes;
- database contention.

It also produces better freshness throughout the day.

---

# 27. Initial Scale

The initial target is approximately:

```text
5,000 startups
```

Example:

```text
London       500
Manchester   100
Munich       350
Berlin       ...
Other cities ...
```

At a 48-hour baseline:

```text
5,000 / 48
≈ 104 companies/hour
≈ 1.7 companies/minute
```

At a 24-hour baseline:

```text
5,000 / 24
≈ 208 companies/hour
≈ 3.5 companies/minute
```

This is manageable with a small worker pool.

The design should nevertheless allow horizontal scaling.

---

# 28. Queue Architecture

The ingestion system should be asynchronous:

```text
Scheduler
    ↓
Queue
    ↓
Workers
    ↓
Database
```

If JobNok uses AWS for production, the conceptual implementation can be:

```text
EventBridge / scheduler
        ↓
SQS
        ↓
Worker processes
```

The exact queue technology can follow the existing infrastructure.

---

# 29. Worker Responsibilities

## Discovery Worker

```text
Startup source
    ↓
Discover startups
    ↓
Normalize
    ↓
Deduplicate
    ↓
Upsert companies
```

## Resolution Worker

```text
Company
    ↓
Find career page
    ↓
Detect ATS
    ↓
Save source
```

## Sync Worker

```text
Company + source
    ↓
Fetch jobs
    ↓
Normalize
    ↓
Deduplicate
    ↓
Upsert
```

---

# 30. Central Job Store

Startup Hunt must use the **same normalized Job store** used by the wider JobNok platform.

Do not create a separate:

```text
startup_hunt_jobs
```

source of truth.

Architecture:

```text
                  Central Jobs
                      ▲
                      │
          ┌───────────┴───────────┐
          │                       │
     Startup Hunt             Recent Search
          │                       │
    ┌─────┴─────┐           ┌─────┴─────┐
    │           │           │           │
   ATS       Generic      Adzuna     TheirStack
```

This allows the same job to appear in multiple JobNok surfaces.

---

# 31. Job Normalization

All providers should map into the central Job schema.

Recommended fields:

```text
id
company_id

title
normalized_title

description

location
country
city

remote_type
employment_type
department

source
source_job_id

source_url
application_url

posted_at
first_seen_at
last_seen_at
closed_at

status

content_hash

created_at
updated_at
```

Exact fields should be aligned with the existing job model.

---

# 32. Job Deduplication

Primary key:

```text
source + source_job_id
```

Fallback fingerprint:

```text
company_id
+
normalized_title
+
normalized_location
+
application_url
```

This is especially important because the same job may be discovered through:

```text
Adzuna
TheirStack
Startup Hunt
Direct ATS
Generic career crawler
```

---

# 33. Job Lifecycle

Jobs should not immediately be marked inactive after one failed/missing synchronization.

Example:

```text
Sync 1:
Job found
→ ACTIVE

Sync 2:
Job found
→ ACTIVE

Sync 3:
Job missing
→ verification pending

Sync 4:
Job still missing
→ INACTIVE
```

Temporary provider failures must not cause mass job deletion.

---

# 34. Failure Handling

Track:

```text
consecutive_failures
last_error
last_successful_sync
```

Use exponential retry/backoff:

```text
1h
2h
4h
8h
24h
48h
```

After successful synchronization:

```text
consecutive_failures = 0
```

Repeatedly failing companies should eventually return to source resolution.

---

# 35. Provider-Level Failure Protection

The system must distinguish:

### Company failure

```text
One company failed
```

from:

### Provider failure

```text
Ashby provider appears unavailable
```

If hundreds of companies using the same provider fail simultaneously, the system should not immediately mark their jobs inactive.

Instead:

```text
Provider health check
        ↓
Provider-wide failure detected
        ↓
Delay mass deactivation
        ↓
Retry
```

---

# 36. High Availability

The ingestion system must be isolated from the user request path.

### User path

```text
User
 ↓
JobNok API
 ↓
Search DB / index
 ↓
Results
```

### Ingestion path

```text
Scheduler
 ↓
Queue
 ↓
Workers
 ↓
Job DB
```

If ingestion is temporarily unavailable, users should continue receiving the latest successfully synchronized jobs.

---

# 37. Freshness Requirements

Initial target:

> **95%+ of active startup jobs should be synchronized within 48 hours.**

For high-priority actively hiring companies:

> **Most job changes should be detected within approximately 12 hours.**

Track:

```text
last_seen_at
last_synced_at
next_crawl_at
```

Metrics:

```text
% active jobs < 12h old
% active jobs < 24h old
% active jobs < 48h old
```

---

# 38. Existing File Responsibilities

## `engine.py`

Continue coordinating the existing Startup Hunt search/provider functionality.

The new ingestion pipeline should feed the normalized job store rather than create another search implementation.

---

## `resolver.py`

Extend the existing resolver.

Responsibilities:

```text
domain
 ↓
career page
 ↓
ATS detection
 ↓
provider selection
 ↓
identifier extraction
```

Example result:

```text
{
    "provider": "ashby",
    "identifier": "example-ai",
    "career_url": "...",
    "confidence": 0.98
}
```

---

## `service.py`

Application-level orchestration.

It should not contain:

- provider-specific scraping logic;
- long-running crawling loops;
- raw HTTP implementation.

---

## `tasks.py`

Background task integration.

It can dispatch:

```text
discover_startups()
resolve_company()
sync_company_jobs()
```

according to the existing task infrastructure.

---

## `models.py`

Extend existing models for:

- company registry;
- source information;
- crawl state;
- scheduling;
- synchronization metadata.

Reuse existing Job models where possible.

---

## `schemas.py`

Add request/response schemas only where the API needs them.

Do not expose internal crawler state unnecessarily.

---

## `routes.py`

Expose only product-facing functionality.

Internal workers should not require HTTP routes to perform ingestion.

---

# 39. StartupMap Crawling

StartupMap should primarily provide:

```text
startup discovery
```

Example:

```text
StartupMap
    ↓
Startup name
    ↓
Domain
    ↓
Country / city
    ↓
Company Registry
```

Then:

```text
Company Registry
    ↓
Official website
    ↓
Official careers page
    ↓
ATS
    ↓
Jobs
```

Before production crawling, the implementation must review and comply with the source's applicable:

- Terms of Service;
- robots.txt;
- crawl restrictions;
- rate limits;
- access controls.

JobNok should minimize requests and avoid unnecessary replication of third-party content.

---

# 40. Security

External URL fetching must implement:

- SSRF protection;
- private/internal IP blocking;
- URL validation;
- redirect validation;
- request timeouts;
- response-size limits;
- safe HTML parsing;
- sanitization of extracted content;
- restricted worker permissions.

The crawler must never be able to use external input to access internal JobNok infrastructure.

---

# 41. Observability

## Discovery metrics

```text
startups discovered
new companies
duplicates
discovery failures
```

## Resolution metrics

```text
career pages found
ATS detected
unknown ATS
resolution failures
```

## Ingestion metrics

```text
jobs fetched
jobs created
jobs updated
jobs closed
duplicates detected
sync failures
```

## Infrastructure metrics

```text
queue depth
worker latency
crawl latency
provider errors
rate-limit responses
```

---

# 42. Source Health

Track provider health independently.

Example:

```text
Ashby
├── requests
├── success rate
├── failure rate
└── latency

Greenhouse
├── requests
├── success rate
├── failure rate
└── latency
```

This allows the system to distinguish provider outages from individual company failures.

---

# 43. User Experience

Users should not need to understand ATS systems.

Instead of asking users for:

```text
ATS provider
ATS slug
company URL
career URL
```

Startup Hunt should present companies directly:

```text
Startup Hunt

Germany
[ Berlin ▼ ]

AI / ML
Software Engineering

--------------------------------

Helsing
AI Engineer
Munich
Posted 4h ago

Example AI
ML Engineer
Berlin
Posted 9h ago
```

Users can eventually:

```text
+ Watch Startup
```

without knowing how the backend finds its jobs.

---

# 44. Relationship With Recent Job Search

Startup Hunt and Recent Job Search should feed the same central Job store.

Example:

```text
Recent Search
    ├── Adzuna
    └── TheirStack

Startup Hunt
    ├── Startup discovery
    ├── Ashby
    ├── Greenhouse
    ├── Lever
    └── Generic career crawler

                  ↓

             Central Jobs
```

A job discovered directly through Ashby can therefore appear in Recent Job Search as well.

This also enables cross-source deduplication.

---

# 45. MVP Scope

## Phase 1 — Discovery

Implement:

- StartupMap source;
- discovery worker;
- company registry;
- company deduplication;
- discovery scheduling.

Target:

```text
1,000–5,000 companies
```

---

## Phase 2 — Resolution

Reuse/extend:

- existing resolver;
- Ashby provider;
- Greenhouse provider;
- Lever provider;
- Google Web provider;
- source registry.

---

## Phase 3 — Ingestion

Implement:

- sync worker;
- provider adapters;
- generic career crawler;
- normalization;
- job upsert;
- job deduplication.

---

## Phase 4 — Reliability

Implement:

- `next_crawl_at`;
- adaptive frequency;
- crawl priority;
- retries;
- exponential backoff;
- provider health;
- stale-job protection.

---

## Phase 5 — Optimization

Implement:

- hiring activity scoring;
- freshness optimization;
- adaptive scheduling based on historical changes;
- additional startup discovery sources;
- additional ATS providers.

---

# 46. Future Capabilities

Once Startup Hunt has accumulated sufficient company/job history, the system can support:

## Hiring Activity

```text
Company X
12 new jobs this month
```

## Hiring Trends

```text
AI hiring
↑ 40%
```

## Startup Watchlists

```text
Watch Company
      ↓
New job detected
      ↓
Notification
```

## Startup Recommendations

```text
Based on your profile:

5 startups hiring AI Engineers
in Germany this week
```

## Hiring History

```text
Company
 ├── current jobs
 ├── previous jobs
 ├── hiring frequency
 └── historical roles
```

---

# 47. Success Metrics

## Coverage

- Number of discovered startups.
- Number of successfully resolved companies.
- Number of companies with known ATS.
- Number of active startup jobs.

## Freshness

- Median job freshness.
- % active jobs synchronized within 12 hours.
- % active jobs synchronized within 24 hours.
- % active jobs synchronized within 48 hours.

## Reliability

- Discovery success rate.
- ATS resolution success rate.
- Job synchronization success rate.
- Queue failure rate.
- Provider error rate.

## Product

- Startup Hunt searches.
- Startup follows.
- Job impressions.
- Job clicks.
- Application clicks.
- Relevant startup-job click-through rate.

---

# 48. Acceptance Criteria

The MVP is considered successful when:

### Discovery

- [ ] StartupMap can be processed as a startup discovery source.
- [ ] Companies are normalized and deduplicated.
- [ ] Company records persist in the database.
- [ ] Discovery can run asynchronously.

### Resolution

- [ ] Existing resolver can resolve discovered companies.
- [ ] Ashby companies are detected.
- [ ] Greenhouse companies are detected.
- [ ] Lever companies are detected.
- [ ] Career pages can be discovered when the ATS is unknown.
- [ ] Resolution results are persisted.

### Ingestion

- [ ] Resolved companies enter the sync queue.
- [ ] Existing ATS providers fetch jobs.
- [ ] Jobs are normalized into the central Job model.
- [ ] Duplicate jobs are prevented.
- [ ] Job status is updated safely.
- [ ] Failed syncs retry automatically.

### Scheduling

- [ ] Companies have `next_crawl_at`.
- [ ] Companies are not all crawled simultaneously.
- [ ] Crawl frequency can vary by priority/activity.
- [ ] Repeated failures back off.
- [ ] Successful synchronization resets failures.

### Reliability

- [ ] Ingestion failure does not block user search.
- [ ] Provider-wide failures do not mass-close jobs.
- [ ] Crawler requests have timeout and SSRF protection.
- [ ] Basic crawl and provider metrics are available.

---

# 49. Final Architecture Decision

Startup Hunt remains **one bounded module**.

It contains three asynchronous responsibilities:

```text
┌─────────────────────────────────────┐
│            STARTUP HUNT             │
│                                     │
│  Discovery      Resolution     Sync │
│      │              │            │  │
│      ▼              ▼            ▼  │
│  "Find          "Find where   "Find │
│  startups"      they hire"    jobs" │
│                                     │
└──────────────────────┬──────────────┘
                       │
                       ▼
                Central Job Store
                       │
              ┌────────┴────────┐
              ▼                 ▼
        Startup Hunt       Recent Search
```

The existing provider architecture remains the core integration layer.

The new architecture **builds on top of the current codebase instead of replacing it**.

The fundamental data flow is:

```text
Startup directories
       ↓
Company discovery
       ↓
Company registry
       ↓
Career/ATS resolution
       ↓
Existing ATS providers
       ↓
Generic crawler fallback
       ↓
Job normalization
       ↓
Job deduplication
       ↓
Central Job Store
       ↓
All JobNok search surfaces
```

## Final architectural principle

> **Discover broadly. Resolve intelligently. Fetch from original sources. Normalize centrally. Deduplicate globally. Crawl adaptively.**

This design keeps the current modular monolith clean while allowing Startup Hunt to grow from approximately **5,000 startups to tens of thousands of monitored companies** without turning the application into an unmanageable crawler.
