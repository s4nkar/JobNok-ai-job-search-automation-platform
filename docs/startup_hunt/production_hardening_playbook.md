# Startup Hunt: Production Hardening Playbook

**Status:** Production-Ready  
**Last Audited:** 2026-08-27  

This playbook establishes operational procedures, safety guards, and resilience patterns for **Startup Hunt**.

---

## 1. Safety & Hardening Checklist

- [x] **SSRF Network Protection**: All outgoing HTTP requests pass through `ssrf_guard.py` (`SafeHTTPClient`), enforcing strict DNS resolution, IPv4/IPv6 private subnet checks, and metadata endpoint blocking (`169.254.169.254`).
- [x] **Rate Limiting ATS Endpoints**: Per-host rate limits prevent IP bans from Greenhouse (`boards.greenhouse.io`), Lever (`jobs.lever.co`), and Ashby (`jobs.ashbyhq.com`).
- [x] **Circuit Breaker Isolation**: External search providers (DuckDuckGo HTML, TheirStack, Apollo) are wrapped in `circuit_is_open()` guards with automatic backoff.
- [x] **Database Worker Locking**: Asynchronous background workers (`resolution_worker`, `sync_worker`) use `FOR UPDATE SKIP LOCKED` queries to guarantee thread-safe task processing across scaling worker replicas.
- [x] **Duplicate Registry Defense**: Company discovery uses partial unique indexes on `company_registry(domain) WHERE domain IS NOT NULL` to handle null-domain records cleanly.

---

## 2. SSRF Guard Verification Procedure

To verify SSRF defenses in a staging environment:

```bash
# Attempt to trigger resolution against AWS metadata service
curl -X POST "http://localhost:8000/api/v1/startup-hunt/sources/resolve" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"company_or_url": "http://169.254.169.254/latest/meta-data/"}'
```

**Expected Outcome**: Endpoint returns HTTP `400 Bad Request` or `422 Unprocessable Entity` with error message containing `SSRF violation: blocked IP 169.254.169.254`.

---

## 3. Distributed Worker Health Checks

Check worker queue processing health in Redis:

```bash
# Check queued resolution jobs count
redis-cli -u $REDIS_URL LLEN arq:queue:startup_hunt_resolution

# Check worker health keys
redis-cli -u $REDIS_URL KEYS "arq:healthcheck:*"
```
