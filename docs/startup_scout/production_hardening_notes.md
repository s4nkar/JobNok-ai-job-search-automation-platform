# Startup Scout — Production Hardening Notes

**Status:** Phase A (discovery/search) hardened (2026-08-28). Phase B
(founder/contact crawl, reached from Tracker's UI) hardened separately on
2026-11-06 - see "Phase B hardening" section below. Both phases are now
production-ready; Phase B's UI entry point is currently disabled by
product decision (low adoption + DDG shared-IP risk vs. a free client-side
alternative), not because it's unreliable.

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
- The DDG mojibake character-encoding issue (some accented characters render
  as `�`) - traced to the third-party `ddgs` library's own response
  handling, upstream of this codebase; not something worth patching a
  vendored dependency for.

---

## Phase B hardening (2026-11-06)

The gaps this doc previously deferred ("BackgroundTasks vs ARQ, in-process
cancel flags") were picked up in a dedicated pass, discovered via a live
audit of `service.py::run_crawl` rather than a checklist walk - reading the
actual orchestration code surfaced several more concrete bugs beyond the
two originally flagged. All verified against the real stack (not just unit
tests): triggered an actual crawl through the full ARQ pipeline end to end,
confirmed the worker picked it up, confirmed final `crawl_status`/saved
contacts in the DB, and separately confirmed the stuck-crawl sweep's query
correctly selects a row orphaned mid-test.

1. **FastAPI `BackgroundTask` → real ARQ job.** `run_crawl` is multi-minute
   sequential work (deliberate pacing sleeps between DDG/Apollo calls) -
   exactly what this codebase's own convention ("heavy work = FastAPI/ARQ")
   says shouldn't run in-process. Registered in `arq_worker.py` with a 600s
   per-task timeout override (the class-wide `job_timeout=30` is sized for
   a single Resend call, nowhere close to enough here). Caveat worth
   remembering: the ARQ **worker** container does not hot-reload the way
   the API's `uvicorn --reload` does (`docker-compose.yml`'s worker command
   is a plain `arq ...`, no watcher) - a code change to `run_crawl` or
   anything it imports needs a manual `docker restart` of the worker
   container to actually take effect, which cost real debugging time in
   this pass (a job sat `queued` with zero errors for several minutes
   before the restart was identified as the cause).

2. **In-process `_cancel_flags` dict → Redis.** Replaced with
   `get_cached`/`set_cached`/`delete_cached` keyed
   `scout_crawl_cancel:{company_id}` (~30min TTL, fails open on a Redis
   error). The old dict only worked with exactly one worker process and
   forgot every pending cancel on restart.

3. **Race condition on double-trigger.** `start_crawl`'s "already crawling"
   check used to read whatever was committed *before* the request - the
   actual flip to `crawling` happened inside `run_crawl`, i.e. after the
   HTTP response triggering the enqueue had already gone out. Two rapid
   clicks (or two tabs) could both pass the check before either job
   started: duplicate Apollo spend, and a delete-then-insert race between
   the two crawls. Fixed by flipping and **committing** `crawl_status`
   synchronously inside `start_crawl`, before the job is even enqueued.

4. **Data loss on failed re-crawl.** Old contacts were deleted
   unconditionally right after flipping to `crawling`, before any new
   source had been tried. A crawl that found nothing at all (DDG blocked,
   Apollo also empty) silently wiped out a prior successful crawl's good
   data. Now deferred: contacts are only cleared once a new source
   actually returns something to replace them with.

5. **Orphaned `crawling` status, no recovery.** A worker crash mid-`run_crawl`
   (or, in dev, a code change triggering the restart described in #1) skips
   the `finally` block that resets status - the row is stuck on `crawling`
   forever, and the frontend's own "can retry" check explicitly excludes
   that status. Added `sweep_stuck_scout_crawls`, a cron job (every 10 min,
   `startup_scout_crawl_stuck_after_minutes` default 10) that re-enqueues
   any company stuck in `crawling` past that threshold - same idiom as
   `sweep_stuck_resolutions`/`sweep_stuck_email_sends` elsewhere in this
   codebase. Verified live by accident: an early test in this pass left a
   row genuinely stuck in `crawling` (a script connected to the wrong Redis
   instance, so its enqueued job was never picked up), which became the
   first real test case for this sweep's query logic.

6. **Unbounded Apollo spend.** Apollo is a paid per-call API; the only
   existing guard was the per-user daily crawl-count rate limit, which
   doesn't cap total deployment-wide spend as user count grows. Added
   `apollo_daily_call_budget` (default 200) via the same `check_tool_budget`
   primitive the AI provider chain already uses - fails closed (skips the
   call, returns no contacts) once exhausted, since this call costs real
   money, not just fails open like a cache miss would.

7. **Redundant re-verification.** After an Apollo supplement, the
   enrich/verify stages used to re-run over *every* saved contact again,
   including ones already verified in the first pass - wasted DDG calls and
   crawl time for no new information. Now scoped to only the newly-imported
   contact IDs.

8. **Name-extraction validation gap.** A real crawl (company "foom")
   produced contacts named "Primary Job Title" and "Primary Organization
   Foom" - structured-data field labels, not people, that passed the
   name-shape check purely because they were capitalized and hadn't been
   added to the stopword blocklist. Separately, `_parse_linkedin_person`
   maintained its own weaker copy of the same validation (missing the
   stopword list entirely, and no single-letter-word rejection), which let
   through a privacy-truncated LinkedIn surname ("Del L") that the general
   path's validator would have caught - except an existing test
   (`test_parse_linkedin_person_strips_multi_profile_concatenation`, using
   "Selin K") proved that exact shape is legitimate, real LinkedIn data, not
   noise. Fixed by: expanding the stopword list (field-label words, plus
   the job-title words `_parse_linkedin_person`'s separate regex used to
   check for) and merging the two validators into one
   (`_is_valid_person_name`) with an `allow_single_letter_word` flag so the
   LinkedIn path keeps its legitimate tolerance while the general snippet
   path keeps rejecting single-letter noise. Three regression tests added.

9. **UI: disabled, not removed, by product decision.** Separate from the
   reliability fixes above - given low adoption (2 enriched companies, 9
   contacts total in the live DB at the time of this pass) and the
   shared-egress-IP DDG risk (heavy Scout usage from any one user can get
   the *entire deployment* rate-limited by DuckDuckGo, not just that
   user's own crawls), the product call was to keep this pipeline working
   but stop surfacing it as the primary path. "Start Crawl"/"Re-crawl"/
   "Stop" now render `disabled` under an "Advanced crawl · Currently
   unavailable" dropdown item; the default action is a free, client-side
   "Find Founders" link (opens a pre-filled Google search in the user's own
   browser - zero backend calls, zero cost, zero DDG risk). Nothing backend
   was deleted; every fix above still applies if this gets re-enabled.
