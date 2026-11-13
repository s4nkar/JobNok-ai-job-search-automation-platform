# My Docs — Production Hardening Playbook

**Status:** Production-ready, one migration pending apply (2026-11-13)

This covers a full production audit of the "My Docs" surface — a
frontend aggregation page with no backend of its own, pulling from
`resume_tailor`, `cover_letter`, and `interview_prep`'s session
list/detail/rename endpoints. The audit was deliberately broad (ownership,
rate limiting, input validation, pagination, FK behavior, race
conditions, cross-module consistency, test coverage, frontend scaling)
before any fix was made, following the pattern used for Tracker's own
hardening pass.

---

## 1. Session detail/reopen endpoints had zero rate limiting

**Found**: in all three modules, `GET .../sessions/{id}` (the endpoint
used when reopening a document from My Docs) had no `check_burst_limit`
call at all — the list and rename endpoints in the same files did. Not
exploitable (every query is already `user_id`-scoped, so it can only ever
read the caller's own rows) but inconsistent with the rest of the CRUD
surface and genuinely unprotected against a scripted loop hammering it.

**Fix**: added the same burst-window check (`resume_tailor_sessions_detail`
/ `cover_letter_sessions_detail` / `interview_sessions_detail`) to all
three, fail-open on Redis error like every other limiter in this
codebase.

**Verified**: `ruff check`, full `pytest` suite (149 passing), live
container reload with no import errors (`docker logs` — see §6).

---

## 2. `resolve_session`'s upsert had no DB-level race protection

**Found**: `cover_letter/service.py::resolve_session` and
`interview_prep/service.py::resolve_session` both do a plain
check-then-act upsert (`SELECT` via `get_by_source`, then `INSERT` or
`UPDATE`) with no DB-level barrier against two concurrent requests for
the same job both missing the `SELECT` and both `INSERT`ing — neither
table had a unique constraint on the linkage columns. The only existing
protection was a **per-user** Redis single-flight lock taken in
`routes.py` before `resolve_session` is even called — real protection
under normal operation, but it fails open if Redis is unreachable
(explicitly documented at the call site: "fail open, same philosophy as
every other limiter here"), at which point two near-simultaneous
requests for the same job could both pass the now-unprotected check and
both insert, producing two session rows for one job.

A second, related finding: the lock itself was scoped **per-user**, not
per-job (`cover_letter_gen:{user_id}:lock`), unlike `resume_tailor`'s
equivalent lock which is scoped per-job
(`tailor_job:{user_id}:{job_id}:lock`) — meaning generating a cover
letter for Job A blocked generating one for Job B at the same time, for
no correctness reason.

**Fix** (two parts):
1. **DB-level backstop**: partial unique indexes on
   `(user_id, source_opportunity_id)` / `(user_id, source_application_id)`
   / `(user_id, source_job_application_id)` for both tables (6 indexes
   total) — migration `f6a9c2e5b831`. `resolve_session` in both modules
   now wraps the `INSERT` in a `SAVEPOINT` (`db.begin_nested()`) and
   catches the resulting `IntegrityError`, falling back to re-fetching
   the row that won the race and updating it instead of erroring the
   user's request.
2. **Lock scope aligned to `resume_tailor`'s pattern**: `cover_letter`
   and `interview_prep`'s generation lock keys now include the job id
   when one is known (`cover_letter_gen:{user_id}:{job_id}:lock` /
   `interview_gen:{user_id}:{job_id}:lock`), falling back to a per-user
   key only for a genuinely ad-hoc generation with no job link.

**Verified**: `ruff check`, full `pytest` suite. Confirmed via a
read-only query against the live DB that zero existing rows would
violate the new unique indexes before writing the migration (so it will
apply cleanly). Live container reload clean (§6). **The migration
itself has not been applied to the database** — `alembic upgrade head
--sql` was used to validate the generated SQL without executing it, per
this session's policy of not running destructive/live-DB-write commands
without explicit approval. Run `uv run alembic upgrade head` from
`apps/api` to apply it.

---

## 3. `cover_letter_sessions.resume_text` had a schema cap with no matching DB check

**Found**: every other text column on `cover_letter_sessions` has a
Pydantic `max_length` *and* a matching DB `CheckConstraint` (this
codebase's standing "belt and suspenders" convention) — `resume_text`
had the Pydantic side (`max_length=8000` on `CoverLetterRequest`) but no
DB-level check at all, the one asymmetric column on that table.

**Fix**: `CheckConstraint("resume_text is null or char_length(resume_text)
<= 8000", ...)` added in the same migration as §2's fix. Model's
`__table_args__` updated to match (so a future `alembic revision
--autogenerate` doesn't propose dropping what it doesn't know about).

**Verified**: existing schema test
(`tests/cover_letter/test_schemas.py::test_cover_letter_request_resume_text_max_length`)
already pinned the Pydantic-layer boundary; the DB layer now matches it.
Not independently tested at the DB layer (no DB-fixture test
infrastructure exists in this codebase — see §5).

---

## 4. All three list endpoints are unbounded (no pagination)

**Found**: `list_sessions_for_docs_page` in all three modules calls
plain `UserScopedRepository.list()` — every row for the user, no
`limit`/`cursor` — despite the shared repository already exposing a
fully-built keyset-cursor `list_page()` (the same method Tracker's four
endpoints use). `resume_tailor`'s version additionally does real
per-row work on every call: a batch `SELECT ... IN` for linked
opportunities/applications, and a full Jinja HTML render for every
session with a saved draft.

**Decision: documented, not fixed, in this pass.** Unlike Tracker's
Scout tab (which can grow by hundreds of scraped rows in a single crawl),
every row here is created by a rate-limited human action (a tailor, a
save, a generation) — natural growth is far slower. More importantly,
My Docs groups *across* all three lists client-side; paginating each
list independently would either break cross-list grouping (a resume on
page 1 pairing with a cover letter that landed on page 3) or require a
server-side "grouped item" pagination redesign, which is a materially
bigger lift than today's actual usage pattern justifies. Flagged as a
scaling characteristic to revisit if evidence of real usage at hundreds
of documents per user appears — see `architecture_lld.md` §3 for the
concrete behavior at that hypothetical scale (3 unpaginated responses,
an O(n) client-side group/sort/filter pass per render, 500+ simultaneous
DOM nodes with no virtualization).

---

## 5. Test coverage: what exists, what doesn't, and why

**Found** (pre-audit state): across all three modules, the only tests
were pure-function/pure-schema unit tests — `_session_display_label`
(cover_letter, interview_prep) and generation-request schema boundary
tests. Zero coverage existed for ownership/IDOR, rate limiting,
pagination, FK `ON DELETE` behavior, or the race condition in §2 — and
none of the three `TitleUpdateRequest`-equivalent schemas had any test
at all.

**Fix**: added boundary tests for `TitleUpdateRequest` /
`CoverLetterTitleUpdateRequest` / `InterviewPrepTitleUpdateRequest`
(accepts a valid title, rejects 201 chars, accepts exactly 200) across
all three modules' `test_schemas.py` files — the one gap in this list
that was genuinely cheap to close at the same abstraction level the rest
of the codebase already tests at.

**Explicitly not added, and why**: a DB-backed integration test for
ownership scoping, the race-condition fix, FK-null-on-delete behavior,
or pagination. **This codebase has no DB-fixture test infrastructure at
all** — no `conftest.py` wiring a test database, no DB-touching test
anywhere under `apps/api/tests/`, for any module, not just this one
(confirmed by directory search during the audit; Tracker's own hardening
playbook notes the identical limitation). Building that infrastructure
from scratch to cover just this module would be inconsistent with how
every other module in this codebase is tested, and is a large enough
undertaking (test DB provisioning, migration-in-test, async fixture
lifecycle) to warrant its own decision rather than being bundled
silently into this pass. The DB-level guarantees added in §2 and §3 were
instead verified the same way Tracker's DB-touching changes were: a
read-only query against the live dev database (§2), `alembic upgrade
head --sql` to validate generated SQL without executing it, and a live
container reload with clean logs (§6).

---

## 6. Live verification performed

- `uv run ruff check` across all three modules and their tests — clean.
- `uv run pytest` across `tests/cover_letter`, `tests/interview_prep`,
  `tests/resume_tailor` — 149 passed (143 pre-existing + 6 new).
- `docker logs` on the live API container after every backend change —
  confirmed `WatchFiles` reload succeeded and `/api/health` kept
  returning `200` throughout, for every file touched (matches this
  codebase's standing practice of checking live container health after
  a backend change, not just `pytest`, after an earlier incident where
  `pytest` alone missed a real `ImportError`).
- Read-only query against the live dev database confirming zero
  existing `(user_id, source_*_id)` duplicates across both tables before
  writing the new unique-index migration.
- `alembic upgrade head --sql` to confirm the new migration's generated
  SQL matches intent, without executing it against the database.
- `tsc --noEmit` / `eslint` on the frontend view-lock changes (covered
  under the session's earlier interview-prep/cover-letter work, not
  re-run here since no frontend files changed in this audit pass beyond
  what was already verified).

---

## What's explicitly *not* done (accepted tradeoffs)

- **Migration `f6a9c2e5b831` has not been applied to the database.**
  This session's policy treats a live-DB write as requiring explicit
  user approval; the Bash tool call to run `alembic upgrade head`
  against the real database was denied by the auto-mode classifier as a
  destructive/live-write action. **Action required**: run
  `uv run alembic upgrade head` from `apps/api` to apply it. The
  read-only pre-check (§2) confirms it will apply cleanly.
- **No pagination on the three list endpoints** — see §4's reasoning.
- **No `is_ai_matched` equivalent on interview_prep's summary** despite
  having an analogous AI-derived-label fallback tier — a cosmetic
  parity gap, not a bug; see `architecture_lld.md` §2.
- **No DB-integration test coverage** — see §5's reasoning.
