# Startup Scout — Production Hardening Notes

**Status:** Phase A (discovery/search) hardened (2026-08-28). Phase B (founder/contact crawl, reached from Tracker's UI) explicitly **not** touched in this pass - it has its own separate reliability gaps (FastAPI `BackgroundTasks` instead of ARQ, an in-process `_cancel_flags` dict) that weren't in scope here.

Checked against `docs/recent_job_search/production_hardening_playbook.md`'s
checklist. Rather than repeat that document's explanations, this only records
what was true for Startup Scout specifically and what changed - see that
playbook for the reasoning behind each pattern.

## Already covered, from the same session that removed the paid APIs

- **Multi-provider cost ordering**: TheirStack and Crunchbase's paid API were
  removed entirely (`engine.py`) - the user's explicit call, not a technical
  finding. DDG scraping is now the sole live-fetch source.
- **Two-layer caching**: L1 Redis response cache (`service.py::search_startups`,
  `startup_scout_response_cache_ttl_seconds` = 6h, much longer than
  job_search's 900s since company data is far more stable than job postings)
  and L2 DB-first (`company_registry`, the crawler's own global company
  table - reused rather than building a new cache table).
- **Single-flight lock + TTL jitter**: same `acquire_lock`/`jittered_ttl`
  primitives as job_search/startup_hunt, same shape.
- **Write-back**: newly-scraped companies feed back into `company_registry`
  via the existing `discovery_service.upsert_discovered` (no duplicated
  upsert logic).

## Added in this pass

1. **Input validation** (`schemas.py`) - had none before: no length bounds on
   any field, no range check on `limit`. Now every field has a `max_length`,
   `funding_stages` is validated against the actual known stage vocabulary
   (rejects garbage instead of silently no-op filtering), `limit` is
   `ge=10, le=200` matching what `engine.search_startups` was already
   silently clamping to - now an invalid value gets a real 422 instead of
   being silently coerced.

2. **Per-user burst limit** (`routes.py::_burst_check`) - only a daily quota
   existed (20 searches/day). Reuses the same generic
   `check_burst_limit`/`rate_limit_burst_limit`/`rate_limit_burst_window_seconds`
   primitives job_search already established - not new plumbing.

3. **Circuit breaker for DDG** - DDG is now the sole live-fetch source, but
   had no circuit breaker at all; a hard rate-limit would have meant every
   one of a search's ~7-14 queries separately paying the full timeout.
   Required a small refactor: `_ddg_search` (used by Phase B, unchanged
   behavior - swallows errors, returns `[]`) is now a thin wrapper around a
   new `_ddg_search_raw` (raises on failure), and only Phase A's own query
   loop in `search_startups` uses the raw version, wrapped with
   `circuit_is_open`/`record_provider_result("startup_scout", "ddg", ...)` -
   the same shared primitives every other tool's provider circuit breaker
   uses. Verified live: 3 forced failures via `record_provider_result`
   tripped `circuit_is_open` to `True`.

4. **Explicit DDG timeout** - `DDGS()` was being constructed with no
   arguments; reading the installed `ddgs` library's source confirmed its
   own default is a real 5s timeout, not unbounded, so this wasn't silently
   broken - but relying on an unexamined third-party default is exactly what
   the playbook's checklist warns against. Made explicit via
   `startup_scout_ddg_timeout_seconds` (default 8s) so it's visible and
   tunable without reading the library.

5. **DB indexing** - `_company_registry_candidates` (new in this session)
   filters with `ILIKE '%token%'` on `city`/`country`, the exact
   leading-wildcard pattern the playbook's own jobs.title/description
   precedent (migration `a22ae866fa45`) already identified as unable to use
   a plain B-tree index. Confirmed via `EXPLAIN`: a `Seq Scan` at 672 rows
   (cheap today, not once the crawler keeps growing this table). `pg_trgm`
   was already installed; added GIN trigram indexes on both columns
   (migration `524f297bbadf`, `CompanyRegistry.__table_args__` updated to
   match so a future `alembic revision --autogenerate` doesn't propose
   dropping them). Verified with `SET LOCAL enable_seqscan = off`: the
   planner now has a real `Bitmap Index Scan` path via both new indexes.

6. **Mobile/tablet layout** - the results grid was a bare
   `grid-cols-[300px_1fr]` with no responsive breakpoint at all (unlike
   job_search/startup_hunt's `grid-cols-1 lg:grid-cols-[320px_1fr]`), and the
   filter `<aside>` was unconditionally `sticky` with no mobile collapse
   toggle and no `max-h`/`overflow-y-auto` - the same sticky-panel-overflow
   bug fixed on the other two tools earlier this session, just never applied
   here since this page predates that fix. Rebuilt to match: `lg:`-gated
   two-column grid, `lg:sticky lg:top-6 lg:max-h-[calc(100vh-8.5rem)]` with
   internal `scrollbar-thin`/`scroll-fade-y` scroll, and the same
   collapsible mobile filter-toggle button pattern. Also added `flex-wrap`
   to the results pagination row (up to 9 buttons + a count label could
   exceed 375px in one non-wrapping row).

7. **Removed, not hardened**: the Export CSV feature (page header button +
   `downloadCSV`/`papaparse` usage) - explicit product call to drop it here,
   revisit under Tracker later if wanted. Also dropped the dead summary
   banner (`meta.total`/`queries_run`/source-chips/"Searched:" line) per the
   same conversation, and gated the per-card source-provenance pill behind
   `NODE_ENV === 'development'` (kept in the API response/cache - legitimate
   debugging data - just not rendered for end users in production).

## Explicitly not done (same spirit as the original playbook's own list)

- Global daily budget for DDG - not added. Unlike Adzuna/Crunchbase, DDG has
  no per-account metered quota to protect; it's now bounded by the 6h
  response cache + company_registry-first layer instead, the same reasoning
  the original playbook used for Arbeitnow.
- Phase B's reliability gaps (BackgroundTasks vs ARQ, in-process cancel
  flags) - real, previously identified, explicitly deferred by product
  decision to a separate pass.
- The DDG mojibake character-encoding issue (some accented characters render
  as `�`) - traced to the third-party `ddgs` library's own response
  handling, upstream of this codebase; not something worth patching a
  vendored dependency for.
