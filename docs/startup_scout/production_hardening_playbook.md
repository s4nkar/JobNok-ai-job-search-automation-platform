# Startup Scout: Production Hardening Playbook

**Status:** Production-Ready  
**Last Audited:** 2026-08-28  

This playbook documents operational hardening measures, DDG circuit breaker behavior, caching topology, and mobile responsive layout fixes for **Startup Scout**.

---

## 1. Production Hardening Summary

### 1.1 Live Fetch & Cost Optimization
- **Sole Source Architecture**: Removed paid API dependencies (TheirStack, Crunchbase API). Live data fetches run exclusively through DuckDuckGo HTML scraping (`html.duckduckgo.com/html`).
- **Two-Layer Caching**:
  - **L1 Redis Hot Cache**: `startup_scout:response:<sha256>` with 6-hour TTL (`21600s`).
  - **L2 DB Global Cache**: Reuses `company_registry` trigram search index before initiating external network queries.

### 1.2 Resiliency & Circuit Breakers
- **DDG Circuit Breaker**: Wrapped in `circuit_is_open("startup_scout", "ddg")`. If DDG emits consecutive rate limits (HTTP 202/429), the circuit opens to prevent hanging worker threads.
- **Explicit Timeouts**: Enforces `startup_scout_ddg_timeout_seconds` (default 8s) to prevent unhandled connection hangs.
- **Fail-Open Rate Limiter**: Per-user burst limiter (`_burst_check`) catches double-click search loops without blocking operational search requests if Redis experiences a temporary failover.

---

## 2. PostgreSQL Trigram Search Indexing

To support fast location and keyword filtering over thousands of discovered companies without table scans:

```sql
-- Migration 524f297bbadf: GIN trigram indexes on city and country
CREATE INDEX company_registry_city_trgm_idx 
    ON company_registry USING gin (city gin_trgm_ops);

CREATE INDEX company_registry_country_trgm_idx 
    ON company_registry USING gin (country gin_trgm_ops);
```

**Verification Command**:
```sql
EXPLAIN ANALYZE 
SELECT * FROM company_registry 
WHERE city ILIKE '%Berlin%' AND country ILIKE '%DE%';
```
*Result*: Evaluates via `Bitmap Index Scan` using `company_registry_city_trgm_idx` rather than `Seq Scan`.

---

## 3. Operations & Maintenance Playbook

### 3.1 Trip & Test Circuit Breakers
To simulate DDG rate limits and verify circuit breaker opening in staging:

```bash
# Force trip DDG circuit breaker in Redis
redis-cli -u $REDIS_URL SET "circuit:startup_scout:ddg" "1" EX 300
```

### 3.2 Clear Stale Scout Caches
```bash
# Clear all Startup Scout hot response keys
redis-cli -u $REDIS_URL KEYS "startup_scout:*" | xargs redis-cli -u $REDIS_URL DEL
```
