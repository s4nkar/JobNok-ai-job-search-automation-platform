# Recent Job Search: Low-Level Design (LLD)

**Document Version:** 2.0.0  
**Status:** Approved for Production  
**Target Audience:** Software Engineers, Module Owners  

---

## 1. Code Architecture & Component Directory

```
apps/api/app/modules/job_search/
├── __init__.py
├── routes.py         # FastAPI HTTP endpoints & dependency injection
├── service.py        # Core workflow, single-flight locking, DB cache lookup
├── scoring.py        # Title match, location/country strict matching logic
├── dedup.py          # Fingerprint hashing & canonical URL deduplication
├── models.py         # SQLAlchemy ORM models (Job, JobSearchApplication)
├── schemas.py        # Pydantic request/response validation DTOs
├── tasks.py          # Async background maintenance tasks
└── providers/
    ├── __init__.py   # Provider registry & spec definitions
    ├── base.py       # Dataclass contracts & base exceptions
    ├── adzuna.py     # Adzuna REST client adapter
    ├── bundesagentur.py # Bundesagentur client adapter
    └── arbeitnow.py  # Arbeitnow API adapter (Bonus feed)
```

---

## 2. Core Service Workflows (`service.py`)

### 2.1 Main Orchestration Sequence (`search_recent_jobs`)

```python
async def search_recent_jobs(
    db: AsyncSession,
    user_id: str,
    payload: JobSearchRequest
) -> JobSearchResponse:
```

1. **Rate Limit Gate**: Calls `_check_rate_limit_fail_open(user_id)` checking both 5-second burst limit and daily request quota.
2. **Tracked Application Map**: Executes `_load_user_applications_map()` bounded by `settings.job_search_max_tracked_history` (default 500) to populate `has_applied` status flags.
3. **Hot Response Cache Lookup**: Generates SHA-256 cache key via `_response_cache_key(payload)`. If key exists in Redis, returns formatted response immediately.
4. **Single-Flight Concurrency Lock**:
   ```python
   lock_key = f"lock:{cache_key}"
   acquired = await acquire_lock(lock_key, ttl_seconds=10)
   ```
   If lock cannot be acquired (another worker is actively fetching), awaits lock release or cache population in 250ms polling intervals (up to 2.5s).
5. **Database Cold Cache Fallback**: Queries PostgreSQL via `query_job_cache_candidates(db, ...)` filtering by query keywords and posting age window (`posted_within_hours`).
6. **Async External Provider Fetch**: If DB candidate count is insufficient, fires `asyncio.gather()` across `applicable_providers(country)`:
   - Wraps each provider in `_fetch_provider_jobs_safe()`.
   - Checks `circuit_is_open(provider_name)` before initiating HTTP request.
   - Evaluates `check_provider_budget(provider_name)` to enforce API cost caps.
7. **Scoring & Merging**: Passes raw jobs to `scoring.score_and_rank_jobs()`.
8. **Deduplication**: Filters duplicate listings using `dedup.deduplicate_jobs()`.
9. **Persistence & Cache Update**: Performs bulk PostgreSQL upsert via `_upsert_jobs_cache()` and writes back to Redis with `jittered_ttl(3600, 300)`.

---

## 3. Algorithmic Specifications

### 3.1 Title Keyword Scoring Algorithm (`scoring.py`)

Job title relevance is calculated using word-boundary regex patterns to avoid partial string false positives (e.g. preventing "ML" from matching "VML Company"):

```python
def score_title_match(query: str, title: str) -> float:
    # 1. Normalize strings
    q_tokens = [re.escape(tok) for tok in query.lower().split() if len(tok) > 1]
    t_lower = title.lower()
    
    # 2. Match exact query match (Highest score = 1.0)
    if query.lower() in t_lower:
        return 1.0
        
    # 3. Token-level word boundary match
    matched_count = 0
    for tok in q_tokens:
        pattern = rf"\b{tok}\b"
        if re.search(pattern, t_lower):
            matched_count += 1
            
    if not q_tokens:
        return 0.5
        
    ratio = matched_count / len(q_tokens)
    return round(0.5 + (ratio * 0.4), 2)  # Score scale: 0.5 to 0.9
```

### 3.2 Strict Country Precision Gate (`scoring.py`)

To prevent cross-border listing leaks:
- If `country_code` is explicitly provided in the user's request (e.g. `"DE"`), candidate jobs with a non-matching non-null country code are discarded immediately (`score = 0.0`).
- Jobs with `country_code = None` are excluded from primary search results and routed strictly to the bonus pipeline.

### 3.3 Deduplication & Fingerprinting (`dedup.py`)

Deduplication uses a two-tier comparison model:

1. **Canonical URL Hashing**:
   ```python
   def canonicalize_job_url(url: str) -> str:
       # Strips tracking parameters: utm_*, gh_jid, gh_src, lever-source, ref
       # Normalizes scheme to lowercase, strips trailing slashes and query fragments.
   ```
2. **Composite Fingerprint Hash**:
   ```python
   def compute_job_fingerprint(title: str, company: str, location: str) -> str:
       raw = f"{clean(title)}|{clean(company)}|{clean(location)}"
       return hashlib.sha256(raw.encode("utf-8")).hexdigest()
   ```
   If two jobs share an identical fingerprint, the entry with the most detailed description and newest `posted_at` timestamp is retained.

---

## 4. Resilience & Circuit Breaker Contracts

```python
# Provider execution guard
async def _fetch_provider_jobs_safe(provider_spec: ProviderSpec, query: str, location: str, country: str) -> list[RawJobListing]:
    if await circuit_is_open(provider_spec.name):
        logger.warning(f"Circuit OPEN for provider {provider_spec.name}. Skipping.")
        return []
        
    try:
        results = await provider_spec.fetch(query, location, country)
        await record_provider_result(provider_spec.name, success=True)
        return results
    except Exception as exc:
        await record_provider_result(provider_spec.name, success=False)
        logger.error(f"Provider {provider_spec.name} failed: {exc}")
        return []
```
