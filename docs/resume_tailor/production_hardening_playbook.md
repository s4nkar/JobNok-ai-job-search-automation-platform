# Resume Tailor — Production Hardening Playbook

**Status:** Production-ready (2026-09-09)

Resume Tailor was built incrementally across many sessions and never got the
same hardening pass that Recent Job Search, Startup Hunt, and Startup Scout
already had — those three share a common Redis toolkit
(`app/services/cache.py`) and use it consistently on every expensive or
duplicable endpoint; Resume Tailor only used a fraction of it. This documents
what closed that gap, organized the same way as
`docs/recent_job_search/production_hardening_playbook.md` — what was done,
why, where in the code, and how it was verified. Everything below was found
by auditing the actual code (file:line citations, not assumptions) and cross-
checking it against the three already-hardened tools, not by guessing at
generic best practice.

---

## Quick checklist for hardening another tool

Same checklist as Recent Job Search's playbook — repeated here because this
pass is direct proof it generalizes:

- [ ] A single-flight lock covers the FULL expensive/duplicable path, not just the part that happens to call an LLM — trace every step between "request arrives" and "result cached," not just the obviously-expensive one
- [ ] A cache/dedup check runs *before* any of the work it would make unnecessary, not after — check for this by tracing what the code does BEFORE its own "is this already done?" check
- [ ] A per-user burst limit exists on every write/expensive-read endpoint, not just the ones that happen to call an LLM
- [ ] A circuit breaker exists on every *shared* external-provider gateway, not per-tool — one shared scope per abstraction layer so every caller benefits from the same breaker state
- [ ] Two clients writing the same mutable resource (autosave, draft state) have actual conflict detection, not silent last-write-wins — verify this explicitly, "seems fine" is not evidence
- [ ] Before assuming something needs a cache, check whether the underlying library already caches it (e.g. Jinja's own compiled-template cache) — caching what's already cached adds complexity for zero benefit

---

## 1. Single-flight lock scope was too narrow (and hid a real inefficiency)

**Found**: `POST /tailor` already had a real single-flight lock
(`resume_cache.acquire_prose_lock`, `generation.py::generate_tailor_prose`),
but it only wrapped the LLM prose call. Everything before it — reading the
resume, JD translation/cleaning/chunking, and a real **paid embeddings API
call** (Jina/Cohere) — ran completely unguarded. Two concurrent identical
submissions (double-click, two browser tabs, a frontend retry) each paid for
a duplicate embeddings call before either one ever reached the existing lock.

**A second bug found while tracing the first one**: `job_description` was
translated/cleaned/chunked/**embedded** *unconditionally*, before the code
ever checked whether a matching session already existed
(`get_or_create_session`). Every re-tailoring of an already-seen (resume, JD)
pair — a common case, not an edge case (re-opening a session, a retried
request, a second identical submission) — paid for a wasted embeddings call
it didn't need at all.

**Fix** (`routes.py::tailor_resume`, `cache.py`):
1. `get_or_create_session` now runs immediately after resolving the resume
   version, *before* any JD work happens. If a session already exists, none
   of the translate/clean/chunk/embed/match/prose pipeline runs at all —
   this alone fixed the second bug.
2. The remaining JD-onward work is wrapped in a new lock,
   `acquire_tailor_lock(user_id, resume_hash, job_hash, force_refresh)`,
   mirroring Recent Job Search's exact leader/follower pattern (§9 of that
   tool's playbook): the leader does the real work; a follower polls
   `get_or_create_session` every 0.5s up to 10s for the leader's result, and
   falls through to doing its own work if the wait is exhausted rather than
   hanging forever. Lock TTL is generous (`2 × ai_request_timeout_seconds +
   embedding_request_timeout_seconds + 15`) so it can't expire mid-leader-
   work and let a second request become leader concurrently.
3. `force_refresh` gets its own lock-key namespace (`...{normal|force}:lock`)
   so a forced re-tailor never queues behind an unrelated normal leader for
   the same pair (which would silently hand back a non-forced result) — two
   concurrent force-refresh calls on the identical pair still dedupe against
   each other.

The existing inner `acquire_prose_lock` was left in place unchanged — with
the outer lock now serializing everything ahead of it, it's redundant in
practice but harmless, and removing it wasn't worth the risk for this pass.

**Verified**: `uv run ruff check app/`, `configure_mappers()`, and manual
trace of the control flow for both `force_refresh=False` and
`force_refresh=True` confirming `session` is always set by the final block.
Two real concurrent browser tabs weren't available to test live in this
environment — this is the one item in this pass verified by code trace
rather than live reproduction, flagged honestly rather than claimed as
observed.

## 2. Rate-limit coverage was inconsistent

Several endpoints had partial or zero protection:

| Endpoint | Before | After |
|---|---|---|
| `POST /tailor/{id}/pdf` (WeasyPrint, CPU-heavy) | daily quota only | + burst limit (`resume_tailor_pdf`) |
| `GET /tailor/{id}/original-pdf` | none | burst limit (`resume_tailor_original_pdf`) |
| `GET /resumes` | none | burst limit (`resume_tailor_saved_list`) |
| `PUT /resumes/{slot}` (Cloudinary upload) | none | burst limit (`resume_tailor_saved_upload`) |
| `PATCH /resumes/{slot}` | none | burst limit (`resume_tailor_saved_rename`) |
| `DELETE /resumes/{slot}` | none | burst limit (`resume_tailor_saved_delete`) |
| `GET /resumes/{slot}/file` | none | burst limit (`resume_tailor_saved_file`) |

All via the existing `check_burst_limit(user_id, bucket, rate_limit_burst_limit,
rate_limit_burst_window_seconds)` fail-open wrapper, same pattern already
used for `resume_tailor_draft`/`resume_tailor_title`/`resume_tailor_preview`
— no new mechanism, just filling in endpoints that were missed when the
saved-resumes feature (`saved_resumes_routes.py`) was built.

**Not done, flagged for later** (matching Recent Job Search's playbook
convention of calling out a real gap rather than silently deferring it):
`PUT /resumes/{slot}` is a real Cloudinary-billed write and could arguably
use a daily quota in addition to the burst limit — not added this pass to
avoid inventing a new settings knob without real usage data to size it
against.

**Verified**: `uv run ruff check`, `python -m py_compile` on every touched
file.

## 3. No circuit breaker on the shared AI/embedding gateways

`app/ai/llm/provider.py::_run_chain`/`stream_text` and
`app/ai/embeddings.py::embed` each loop over a provider fallback chain
per-call with zero cross-request memory — a provider that has failed 50
times in the last minute got retried (and its full timeout paid) on the very
next unrelated call, by any tool. Recent Job Search's playbook (§4) already
documents why this matters: an unofficial API changing shape mid-session, or
a provider outage, otherwise costs every affected request a full timeout
until someone notices.

**Fix**: added `circuit_is_open(scope, provider)` before each dispatch
attempt (skip like the existing "not configured" branch) and
`record_provider_result(scope, provider, ok=...)` after each attempt
resolves, in both files. Recorded **once per provider per call** — for the
429-then-retry-succeeds path, once after the retry's outcome, not once for
the initial 429 and again for the retry, so a single rate-limit blip that a
retry recovers from can't trip the breaker on its own.

**Scope choice**: one shared scope per abstraction layer (`"ai_llm"` for
`provider.py`, `"embeddings"` for `embeddings.py`), not one scope per calling
tool. A provider outage is a fact about the provider, not about which tool
triggered the call — Resume Tailor, Cover Letter, Interview Prep, and Salary
all share `provider.py`, so they all benefit from the same breaker state
instead of each independently rediscovering the same outage. This is a
shared-module change, purely additive around existing try/except blocks, no
control-flow change otherwise.

**Verified**: `uv run ruff check`, direct import + `configure_mappers()`
(this repo's WeasyPrint dependency chain can't be imported natively on this
Windows dev host, so `main.py`'s full app can't be booted here — see
"Environment limitations" below). Circuit trip behavior itself (3 failures/
300s trips it, 180s cooldown) is the same already-proven mechanism used by
`job_search`/`startup_hunt`/`startup_scout` — not re-verified independently
here since the mechanism itself is unchanged, only its two new call sites.

**Not done**: no global daily budget (`check_provider_budget`/
`check_tool_budget`) was added for the AI/embedding layer, even though these
are metered, paid calls exactly like Adzuna/Bundesagentur in Recent Job
Search's §13. The per-user daily quota (`resume_tailor_ai`, 8/day) bounds
individual abuse but not aggregate exhaustion the way Recent Job Search's
`job_search_tool_daily_budget` does. Flagged, not fixed — would need real
usage data to size a sane ceiling, same caveat Recent Job Search's own
budget numbers carry.

## 4. Draft autosave had no conflict detection (two tabs could silently clobber each other)

**Found**: `PATCH /tailor/{id}/draft` was plain last-write-wins — no version
check at all. Two browser tabs open on the same session, each autosaving on
its own 1.5s debounce, could silently overwrite each other's edits with zero
indication anything was lost.

**Fix**: optimistic concurrency via a version counter.
- `tailoring_sessions.draft_version` (new column, migration
  `f2a9c6e1d4b8`, default 0) — incremented on every successful draft save.
- `GET /tailor/{id}/editor` now returns `draft_version` so the editor knows
  its starting point.
- `PATCH /tailor/{id}/draft` takes `base_version: int` in the request body.
  `TailoringSessionRepository.save_draft` only writes if `base_version`
  matches the row's *current* `draft_version`; on a match it saves and
  bumps the counter, on a mismatch it returns the row **unmodified** plus a
  `conflict=True` flag. The route turns that into `409` with the current
  winning `cv_data`/`draft_version` in the body, instead of ever
  overwriting content it never saw.
- Frontend (`editor/page.tsx`): a `draftVersionRef` (not React state —
  nothing renders it, and it must not retrigger the autosave effect on its
  own change) tracks the last version this tab saved against. On `200`, it
  advances to the new version. On `409`, the tab **converges to the winning
  state** — replaces its own `cvData` with the server's current draft and
  syncs its version ref — rather than retrying forever against a
  now-permanently-stale `base_version`, with a toast telling the user their
  resume changed in another tab.

**Design choice, stated explicitly**: on conflict, the losing tab's
not-yet-saved keystrokes since its own last successful save are discarded in
favor of the other tab's saved state — no attempt at field-level merging.
This is the same tradeoff most non-realtime-collaborative editors make
(reload-and-inform, not merge) and was chosen deliberately for simplicity
and safety over building actual operational-transform-style merging for a
narrow edge case (same logged-in user, own tabs only).

**Verified**: `uv run ruff check`, `uv run alembic heads` (chain resolves
cleanly through the new migration), `configure_mappers()`,
`pnpm exec tsc --noEmit`, `pnpm exec eslint`, full `pnpm exec next build`
(compiles, all pages generate). Two real concurrent tabs weren't exercised
live in this environment — verified by tracing the version-mismatch branch
end-to-end (repository → route → frontend conflict handler) rather than by
reproducing the race, flagged the same way as §1's lock.

## 5. Template/layout rendering — investigated, no fix needed

Question raised: since all 17 resume layouts are the same static templates
for every user, do they need explicit caching? Traced `rendering.py`:
`_jinja_env = Environment(loader=FileSystemLoader(...))` is a **module-level
singleton**, created once at process startup — `render_html`'s
`_jinja_env.get_template(template_file)` call hits Jinja's own internal
compiled-template cache (keyed by filename) on every call after the first.
The expensive part (parsing the template file off disk, compiling it) already
happens once per process lifetime, not once per request. What varies per
request is only `tmpl.render(**cv_data)` — filling the already-compiled
template with one user's specific data — which is inherently per-user
content that can't be shared across users regardless of caching layer,
and is already cheap (~10ms, no LLM, per the pipeline's own documented cost
profile).

**Conclusion**: no caching gap here. Worth documenting explicitly (per
Recent Job Search's playbook's own precedent of writing up an investigation
that concluded "already fine") so the next person auditing this tool doesn't
re-ask the same question from scratch.

## 6. JD length — two separate limits, only one was worth touching

- **Accepted-input cap** (`_MAX_JD_LENGTH = 20_000` chars, `routes.py`,
  mirrored by a DB CHECK constraint): generous and correctly sized. Real job
  postings rarely exceed ~8-10k characters, and this cap protects the
  deterministic matcher/embedder (which use the *full* cleaned JD text via
  `chunker.py::clean_jd_text`/`chunk_jd`) plus DB storage. Confirmed correct,
  left unchanged — including on explicit user request after this was raised.
- **Separately**, `generation.py` truncates the JD to a fixed length
  specifically for the AI *prose* prompt (headline/summary/bullet rewrites)
  — unrelated to the 20k input cap, and low enough that a JD with company
  boilerplate before its real requirements could get truncated before the
  LLM ever saw the requirements. Investigated (confirmed there's token
  headroom — the "~1.2k tokens" figure in this repo's docs is the prose
  *completion* budget, not the input, which already runs well past that from
  the resume excerpt + system prompt alone) but **left unchanged per
  explicit user decision** — flagged as understood-but-intentionally-not-
  fixed, not silently skipped.

---

## What's explicitly *not* done (accepted tradeoffs)

- No global daily budget for the AI/embedding provider layer (§3) — only a
  circuit breaker. Per-user quota exists; aggregate-exhaustion protection
  doesn't yet.
- No dashboard/alerting for circuit breaker trips on `"ai_llm"`/
  `"embeddings"` — same gap Recent Job Search's playbook already calls out
  for its own provider budgets. Nobody gets notified when a breaker trips,
  it just silently skips that provider for its cooldown window.
- Draft-conflict resolution (§4) is reload-and-inform, not merge — accepted
  tradeoff, not a limitation anyone hit yet.
- Neither of §1's nor §4's concurrency fixes were verified against a real
  two-request race in this environment (no way to drive two genuinely
  concurrent browser tabs or HTTP requests here) — verified by code trace
  instead. Worth a live check (two tabs, or a quick `asyncio.gather` of two
  identical `/tailor` calls) before fully trusting this under real traffic.

## Environment limitations encountered while verifying this pass

`apps/api`'s WeasyPrint dependency requires native GObject/Pango libraries
not installed on this Windows dev host — `import app.main` (and anything
that transitively imports `resume_tailor/rendering.py`) fails at import time
with `OSError: cannot load library 'gobject-2.0-0'`, and the same blocks
`pytest` from even collecting tests that touch this module. This is a
pre-existing environment gap, not something introduced by this pass.
Verification here relied on `ruff check` (this repo's Pyflakes-only lint
config, which reliably catches undefined names/unused imports),
`python -m py_compile`, direct import of the non-WeasyPrint-dependent
modules (`cache.py`, `saved_resumes_routes.py`, `provider.py`,
`embeddings.py`) plus `configure_mappers()` to confirm every FK/model change
resolves, and the frontend's own `tsc`/`eslint`/`next build`. Run the full
`pytest` suite inside Docker (where the native libs are installed) before
treating this as fully verified end-to-end.
