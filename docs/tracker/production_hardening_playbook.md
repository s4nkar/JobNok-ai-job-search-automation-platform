# Tracker — Production Hardening Playbook

**Status:** Production-ready (2026-11-06)

Tracker went through more individual fix passes than any other module in
this codebase's history, across one continuous session: input validation,
cursor pagination, cross-module document linkage, a full mobile layout
pass, and a cross-cutting UI-consistency pass (scrollbars, table cell
wrapping) that reached two shared components used elsewhere in the app
too. This playbook consolidates all of it.

---

## 1. Zero rate limiting, zero length bounds, zero enum enforcement (Applications tab)

**Found**: `ApplicationIn` had no `max_length` on `company`/`role`/`notes`
at either the Pydantic or DB layer, and `status` accepted any string
regardless of the frontend's fixed dropdown — a direct API call could
persist an arbitrary status value the UI had no rendering for. None of
`GET`/`POST`/`PUT`/`DELETE` had rate limiting of any kind.

**Fix**: `company`/`role` capped at 200 chars, `notes` at 3,000, `status`
restricted to a `Literal` matching the frontend's six-value enum — all
three layers (Zod, Pydantic, DB `CheckConstraint`, migration
`a3c7e9f1b5d2`). Burst-window check added to all four endpoints; daily
quota (`rate_limit_tracker_create_per_day`) added to `POST`.

**Verified**: queried the live DB for any row that would violate the new
constraints before writing the migration — table was empty, safe to add
directly. `ruff check`, full `pytest` suite, migration applied and
`alembic current` confirmed at the new head.

## 2. Generic "something went wrong" discarded the backend's actual error

**Found**: the Add/Edit Application form's failure branch always showed a
hardcoded "Something went wrong," regardless of what the backend actually
returned — including FastAPI's own 422 validation-error body (a list of
per-field messages), which was silently thrown away.

**Fix**: `describeApiError(body)` parses both of FastAPI's error shapes
(a plain string for raised `HTTPException`s, a list of field errors for
Pydantic validation failures) and surfaces the specific field + reason
when available. Required fields also got visible `*` markers on their
labels so the user isn't guessing which ones matter before submitting.

## 3. No cursor pagination — every list endpoint returned its entire table

**Found**: `GET /api/tracker`, `/api/startup-hunt/opportunities`,
`/api/startup-scout/companies` had no pagination at all;
`/api/job-search/applications` had a `limit=200` hard cap with no way to
see past it. Fine at today's scale, not sustainable for a tool whose
premise is "nobody deletes a rejected application."

**Fix**: keyset (cursor) pagination, chosen over `OFFSET` specifically
because offset pagination skips/duplicates rows under concurrent writes
(a new row shifts every row below it by one) while a cursor anchored to
`(created_at, id)` doesn't have that problem. Added as `UserScopedRepository
.list_page()` (shared across all four tabs' repositories), opt-in via
optional `limit`/`cursor` query params so every other consumer of these
same endpoints (Dashboard, Startup Hunt's own page, Startup Scout's own
page, Recent Job Search) is unaffected by omitting them. Frontend:
`usePaginatedList<T>` hook, deliberately local `useState` rather than a
react-query cache entry — see `architecture_lld.md` §2.2 for why sharing
the cache key with those other pages would have corrupted what they read.

**Verified**: `ruff check`, full `pytest` suite (691 passing). Confirmed
via `tsc`/`eslint` on every touched frontend file.

## 4. Manually-added tracker rows had no path into My Docs grouping

**Found**: My Docs already grouped a resume + cover letter for the same
Startup Hunt lead or synced Job Search row, via `source_opportunity_id`/
`source_application_id` on each session table. A manually-added
**Application** row — Tracker's own primary tab — had no such column at
all. Worse: the Applications tab's "Use with tools" dropdown sent only
`company`/`role` as plain text to Resume Tailor/Cover Letter/Interview
Prep, no id at all, so this wasn't just a missing grouping feature, it was
a missing *linkage* — those documents could never be found again by job.

**Fix**: a third `source_job_application_id` column added to all three
session tables (migration `c2e5f9b7a814`), same `ON DELETE SET NULL`
shape as the other two. Tracker's "Use with tools" menu now passes
`job_application_id`; each tool's generate endpoint verifies ownership
server-side before storing it (never trusts the client-supplied id
alone). My Docs' `groupKeyFor()` extended to check all three columns.

**Verified**: `ruff check`, full `pytest` suite, `tsc`/`eslint` on every
touched file. Migration applied to the live DB.

## 5. The grouped-docs card layout broke with 3+ documents

**Found**: `JobGroupCard` stacked every linked document vertically in one
narrow grid cell. A 2-document group looked fine; a 3rd document (once
the linkage fix in §4 started actually grouping resume + cover letter +
interview kit together) wrapped into a lone half-width cell with dead
space beside it — a `grid-cols-2` with an odd item count, the classic
CSS-grid orphan-row problem.

**Fix**: switched the inner layout from CSS Grid to `flex flex-wrap`
with each card `flex-1`. Flex items on an incomplete row stretch to fill
it instead of leaving a gap, for any count (2, 3, 4+) with no
breakpoint-specific logic needed.

## 6. Startup Leads' inline "Docs" panel duplicated what My Docs now owns

**Found**: once My Docs could group and show documents properly (§4, §5),
the Leads tab's own inline expandable "Docs" column/panel (reading from a
separate `opportunity_artifacts` table) became redundant — and distinct
from it: generating a document from a lead *also* wrote into this
now-orphaned table via three separate `POST .../artifacts` calls (one
each from Resume Tailor, Cover Letter, Interview Prep), none of which any
UI read anymore after the panel was removed.

**Fix**: removed the inline panel, then traced and removed every write
path into `opportunity_artifacts` (including one in `resume_tailor/
service.py::save_resume_artifact`, triggered from the PDF-export
endpoint — not just the three obvious ones), the model, the service
functions, the routes, and finally the table itself (migration
`b1f4d8a0c6e3`, confirmed empty before dropping).

**Verified**: confirmed zero remaining references anywhere in `app/`
after each removal step; live container logs caught the first attempt's
import error immediately (see §11's note on why pytest alone wasn't
enough here).

## 7. Contact position/title was captured but never shown; then over-shown

**Found**: Startup Scout's contact-enrichment pipeline has always captured
a person's job title (from Apollo's API response, or parsed from their
LinkedIn headline) — it just wasn't rendered on the contact card at all
after an earlier redesign stripped it along with source/citation info the
user explicitly didn't want shown.

**Fix**: re-added the title as a small muted line under the contact's
name, shown only when present — keeping the earlier minimalism decision
(no source badges, no citation links) while restoring the one field that
was genuinely useful and already being captured for free.

## 8. Icon-only buttons and multi-word labels wrapped onto two lines

**Found**: "Start Crawl" (and several other two/three-word button
labels — "View docs" counts, "Edit", "Apply"/"Careers"/"Open") rendered on
two lines inside their fixed-height buttons, because nothing stopped the
text from wrapping at the space. Separately, "Stage"/"Location"/"Source"
pill cells had the same issue for multi-word values (`"Series A"`, a
two-word city name). Root cause, once traced fully: the **shared**
`TableCell`/`TableHead` components (`packages/ui`) had no
`whitespace-nowrap` default at all — every cell in every table in this
app (both consumers: Tracker and Bulk Email) was wrap-prone by
construction, not just the handful of spots first reported.

**Fix**: fixed at the source rather than per-cell — added `whitespace-nowrap`
to the shared `TableCell`/`TableHead` base classes (the `Table` wrapper
already scrolls horizontally via `overflow-auto`, so there's no
correctness reason for a cell to ever wrap instead). Covers every column
in all four tabs, plus Bulk Email, in one change.

## 9. No consistent scrollbar styling across scrollable sections

**Found**: a shared `.scrollbar-thin` utility already existed
(`packages/ui/src/theme.css`, used in Recent Job Search) but was never
applied to Resume Tailor's JD textarea, Cover Letter's selling-points/
resume/output textareas, Interview Prep's JD textarea, or Tracker's own
mobile horizontal table scroll — each showed the browser's default
scrollbar instead. Separately, the utility itself had a real gap:
`::-webkit-scrollbar` only set `width` (thins a *vertical* scrollbar),
never `height` (needed for a *horizontal* one) — so even applying it to
Tracker's horizontal scroll wouldn't have fully worked in Chrome/Safari/
Edge.

**Fix**: baked `scrollbar-thin` into the shared `Textarea` and `Table`
components (same "fix at the source" approach as §8) so every current and
future textarea/table gets it automatically, and added the missing
`height: 4px` to the utility's webkit rule.

## 10. Mobile had no card layout — a table squeezed onto a phone screen

**Found**: all four tabs rendered the same desktop `<Table>` at every
breakpoint. Below `sm`, this meant either illegible column-squeezing or a
horizontally-scrolling row with no good way to see it all.

**Fix**: a parallel card-based render path per tab (see
`architecture_lld.md` §2.4 for the full design), toggled by CSS
breakpoint classes rather than a JS media-query check (no hydration-
mismatch risk, consistent with this page's pre-existing stat-card
pattern). Accepted cost: every tab's markup now exists twice (documented
explicitly, not an oversight — see "What's not done" below).

## 11. Startup Scout's crawl pipeline — FastAPI BackgroundTask, race condition, data loss, orphaned status, unbounded Apollo spend, bad name extraction

**Found and fixed in the same pass, reached from Tracker's Scout tab but
belonging to `startup_scout`'s own codebase**: this is the single largest
set of fixes in this session. Full writeup, including the live
end-to-end verification (an actual crawl run through the real ARQ
pipeline, a genuinely-orphaned stuck row used as a live test case for the
new sweep, and the worker-container hot-reload gotcha that cost real
debugging time) lives in
`docs/startup_scout/production_hardening_notes.md`'s "Phase B hardening"
section — not duplicated here to avoid the two documents drifting out of
sync. Summary: moved to a real ARQ job (was an in-process
`BackgroundTask`), fixed a double-trigger race condition, fixed data loss
on a failed re-crawl, added a stuck-status self-healing sweep, added a
whole-deployment Apollo spend budget, fixed a contact-name-validation gap,
and — a separate product decision, not a bug fix — disabled the feature's
UI entry point in favor of a free client-side "Find Founders" search
link, without deleting any of the now-hardened backend.

---

## What's explicitly *not* done (accepted tradeoffs)

- **No automated test coverage for DB-touching orchestration**
  (`start_crawl`'s race-fix, `run_crawl`'s deferred-delete,
  `sweep_stuck_scout_crawls`, `shared/repository.py::list_page`). This
  codebase's test suite has no DB-fixture infrastructure at all (no
  `conftest.py`, no test database anywhere in `apps/api/tests/`) — a
  pre-existing, project-wide limitation, not something introduced or
  specific to this module. All of the above was verified live against the
  real running stack instead (an actual crawl end-to-end, the stuck-row
  sweep's query logic confirmed against a genuinely-orphaned row). Pure
  logic that *could* be isolated (the field-label/job-title name-
  validation fix) got real unit tests; the DB-touching orchestration
  explicitly did not, by deliberate decision after weighing the cost of
  standing up live-cloud-DB integration tests against this project's
  existing convention.
- **Every tab's UI now exists twice** (desktop table row + mobile card),
  a real ongoing maintenance cost from the mobile pass (§10) — accepted
  because the alternative (a table squeezed onto a phone) was worse, and
  a shared-component abstraction over both would have been premature
  given each tab's card and row differ in exactly which fields matter at
  a glance.
- **`docCountFor`'s minor inefficiency was fixed anyway** (memoized into
  a single precomputed map) despite being flagged as not worth it at this
  app's actual scale — included once asked for explicitly, not because
  it was ever observed to be slow.

## Environment limitations encountered while verifying this pass

- **The ARQ worker container doesn't hot-reload.** Unlike the API's
  `uvicorn --reload`, `docker-compose.yml`'s worker command
  (`arq app.workers.arq_worker.WorkerSettings`) has no file watcher — a
  code change to `run_crawl` or anything it imports sat in the running
  worker's stale in-memory function registry until a manual
  `docker restart` of that one container. Cost real debugging time (a
  job sat `queued` with zero errors for several minutes) before being
  identified. Worth remembering for any future ARQ task change.
- **A live test script connected to the wrong Redis instance once**,
  purely a host-vs-container `.env` resolution difference (the host
  shell's `settings.redis_url` resolved to a different Redis than the
  one the dockerized API/worker actually use) — not a bug in the
  application, but it did produce a real, if accidental, demonstration of
  the stuck-crawl bug §11 fixes, which became a useful live test case for
  the new sweep rather than a wasted detour.
