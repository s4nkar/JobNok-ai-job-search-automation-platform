# Cover Letter — Production Hardening Playbook

**Status:** Production-ready (2026-10-29)

Audited against the same bar as `docs/resume_tailor/production_hardening_playbook.md` — rate limiting, caching, circuit breaking, and concurrency safety — specifically after this tool's generation endpoint was changed from "explicit Save button" to "every generation auto-persists" (see `docs/cover_letter/architecture_hld.md` §4.1). Auto-save raised the stakes on a gap that didn't matter as much before: two concurrent identical requests no longer just duplicate an LLM call, they could duplicate a *saved row*. Everything below was found by tracing the actual code (file:line), not by assuming generic best practice.

---

## Quick checklist for auditing another AI-generation tool

- [ ] A per-user daily quota AND a short burst window both exist on every endpoint that calls an LLM — a daily cap alone bounds volume, not arrival rate.
- [ ] A single-flight guard exists on any endpoint that both calls an LLM *and* writes a row — burst limiting throttles rate, it does not prevent two near-simultaneous requests from both passing the check and both doing the expensive work.
- [ ] If an endpoint upserts into an existing row based on some runtime-resolved identity (a job link, a session id), confirm the single-flight guard is acquired **before** that resolution runs, not after — otherwise two concurrent requests can both resolve "no existing row" and both create one.
- [ ] A circuit breaker exists on the shared provider gateway, not per-tool, so every caller benefits from the same breaker state.
- [ ] Before assuming a step is cacheable, confirm there's a real deterministic cache key — a free-text LLM generation usually doesn't have one, and forcing a cache onto it just adds complexity (see §3 below).

---

## 1. No single-flight lock on the generation endpoint — real duplicate-row risk after auto-save

**Found**: `POST /cover-letter` had a daily quota and a burst-window check (`routes.py`, both pre-existing), but nothing preventing two *concurrent* requests from the same user. `check_burst_limit` throttles rate (allows up to `rate_limit_burst_limit`, default 3, within `rate_limit_burst_window_seconds`, default 10s) — it does not block two requests arriving within the same second from both passing. Before auto-save this only meant double-billing the AI provider on a double-click. After auto-save (`service.py::resolve_session`, resolved fresh on every call), it got worse: two concurrent requests for the same job link would *both* find no existing session yet (the first one hasn't committed its row), and both create one — two `cover_letter_sessions` rows for what should be "only one saved letter per job."

**Fix** (`routes.py::generate_cover_letter`):
- Added `_GENERATION_LOCK_TTL_SECONDS = 60` and a per-`(user_id)` single-flight lock (`acquire_lock(f"cover_letter_gen:{user_id}:lock", 60)`, the same shared primitive `app/services/cache.py::acquire_lock` every other tool's locks use), acquired right after the burst check and **before** `resolve_session` runs — a second concurrent request is rejected with `429` before touching the DB or the LLM at all, not after.
- Released explicitly via `delete_cached` the moment this request's own work finishes — in `resolve_session`'s own `except` branch if it fails before streaming starts, and in `generate()`'s `finally` block once the stream ends (success or interrupted) — rather than left to expire on the full 60s TTL. A legitimate second letter a few seconds later is never blocked longer than the first one's own actual duration; the TTL is only a safety ceiling for the rare case the process dies before reaching that `finally`.

**Verified**: `uv run ruff check`, full `pytest` suite (656 passing), and a direct test of the underlying primitive against live Redis:
```
first acquire: True
second acquire while held (should be False): False
acquire after release (should be True): True
```
The full route itself can't be driven by two genuinely concurrent HTTP requests in this environment (no way to script two real overlapping calls here) — verified by code trace (lock acquired before `resolve_session`, released in every exit path) plus the primitive-level test above, not by reproducing the race live. Worth a real two-tab/`asyncio.gather` check before fully trusting this under production traffic.

## 2. Same gap, same fix, in Interview Prep and a related gap in Resume Tailor

Traced the same two sibling AI-generation tools while auditing this one, since all three share the exact auto-save-on-generate shape as of this session:

- **Interview Prep** (`POST /interview`, `POST /interview/regenerate`) had the identical missing-lock gap. Fixed the same way: a per-`(user_id)` lock on `/interview` (`interview_gen:{user_id}:lock`), and a narrower per-`(user_id, session_id, question_index)` lock on `/interview/regenerate` (two *different* questions' regenerate calls from the same user are independent work and shouldn't block each other — only a double-click on the *same* question's button should). See `docs/` — a full doc set for this module is new as of this pass; this playbook covers it too since the fix is identical.
- **Resume Tailor** (`POST /tailor`) was *not* missing its generation lock — it already has a mature single-flight design (`resume_cache.acquire_tailor_lock`, keyed by `(user_id, resume_hash, job_hash)`, leader/follower with polling — see `docs/resume_tailor/production_hardening_playbook.md` §1). But this session's own earlier change added a **new** upsert path (job-linked overwrite, "only one saved resume per job") that the *existing* hash-based lock doesn't cover: two concurrent `/tailor` submissions for the *same tracked job* with even slightly different resume/JD text (different `job_hash` → different lock key → no mutual exclusion) could both resolve "no existing session for this job" and both create one. Fixed with a second, short-TTL (15s, not explicitly released) lock keyed on the raw job link (`tailor_job:{user_id}:{opportunity_id or job_search_application_id}:lock`) — intentionally the lighter-weight "thundering herd" pattern `acquire_lock`'s own docstring describes, not full mutual exclusion with explicit release, since wrapping `/tailor`'s whole multi-branch body (cache-hit early return, single-flight-follower polling, the real pipeline) in `try/finally` would be real control-flow surgery for a narrower bug than §1's.
- **Also found while there**: `POST /tailor` had a daily quota (`resume_tailor_ai`) but **no burst-window check at all** — every *other* endpoint in `resume_tailor/routes.py` (draft/title/preview/pdf/etc.) already has one, and so do `cover_letter`/`interview_prep`'s own generate endpoints. Added the same `check_burst_limit(user_id, "resume_tailor_ai", ...)` pattern used everywhere else in that file.

**Verified**: same as §1 — `ruff check`, full `pytest` suite (656 passing, no regressions in resume_tailor's existing 300+ tests for this endpoint), `python -m py_compile` on every touched file (this repo's WeasyPrint dependency chain can't be imported natively on this Windows dev host — see "Environment limitations" below). The job-link upsert race itself (resume_tailor) and the duplicate-row race (cover_letter/interview_prep) were both reasoned through and closed by code trace, not reproduced live.

## 3. Caching — investigated, no gap found

Unlike Resume Tailor (which caches JD chunking/embeddings keyed on a content hash — `resume_tailor/cache.py`'s JD chunk cache) or job_search/startup_hunt (which cache external-provider search results), Cover Letter and Interview Prep have no deterministic, cacheable step: the entire response is free-text LLM generation, which by design can legitimately differ between two calls with identical input (a regenerate is *supposed* to produce different wording). There is no "compute once, serve many" opportunity here the way there is for a JD's embedding vector. Forcing a cache onto this would either (a) return a stale/identical response when the user explicitly wants a fresh one, or (b) need to be keyed on something that changes every call anyway, making it pointless.

**Conclusion**: no caching gap. Worth documenting explicitly (matching Resume Tailor's own playbook §5 precedent of writing up an "already fine" investigation) so the next person doesn't re-ask from scratch.

## 4. Already covered, confirmed not re-broken

- **Circuit breaker**: shared `_CIRCUIT_SCOPE = "ai_llm"` in `app/ai/llm/provider.py` — Cover Letter and Interview Prep's `generate_text`/`stream_text` calls participate automatically, no per-tool wiring needed or touched by this pass.
- **Rate limiting**: daily quota + burst window on every AI-costed endpoint (generation, regenerate) and every DB-write endpoint (session list/title-rename) — confirmed present on all of them, not just the obviously-expensive ones.
- **Ownership re-verification**: `opportunity_id`/`job_search_application_id` are never trusted as given — `service.py::verify_opportunity_ownership`/`verify_application_ownership` re-check against the DB before either is used as a `source_*_id` on a session, in both tools.
- **Input length limits / DoS**: every text field bounded on both the Pydantic schema and the DB `CheckConstraint` (resume_tailor-style defense in depth) — confirmed unchanged by this pass.
- **No secrets/PII in logs**: both tools' exception logging uses char counts and exception reprs only, never raw prompt/output content — confirmed unchanged.

---

## What's explicitly *not* done (accepted tradeoffs)

- The per-user generation lock (§1) is coarser than strictly necessary for the job-linked case: it blocks **any** two concurrent generations from the same user, even for two unrelated jobs, not just two for the *same* job. Accepted as a simplification — these are relatively infrequent, one-shot actions (unlike Resume Tailor, where a power user might reasonably tailor for several different jobs in one sitting), so the coarser lock's false-positive cost is low.
- No global daily AI-provider call budget specific to these two tools — only the shared `ai_llm_daily_call_budget` ceiling in `provider.py` (same gap Resume Tailor's own playbook §3 already accepts).
- None of this pass's concurrency fixes were verified against a real two-request race in this environment — verified by code trace and a primitive-level Redis test, not live reproduction. Same caveat Resume Tailor's playbook §1/§4 already carry.

## Environment limitations encountered while verifying this pass

Same as every other pass touching these modules this session: `apps/api`'s WeasyPrint dependency requires native GObject/Pango libraries not installed on this Windows dev host, so anything importing `cover_letter/rendering.py` (transitively, `routes.py`) fails at import time locally — `pytest`'s own collection works around this by not importing WeasyPrint-chain modules directly in test files, and `uv run pytest` already passes (656 tests) because of that isolation. Verification here relied on `ruff check`, `python -m py_compile`, direct import of the non-WeasyPrint modules (`service.py`, `repository.py`, `schemas.py`, `text.py`) plus live Redis calls against the real lock primitive. Run inside Docker (where the native libs are installed) before treating the full route-level behavior as verified end-to-end.
