# Tracker: Low-Level Design (LLD)

**Document Version:** 1.0.0
**Status:** Approved for Production

---

## 1. Code Architecture

### 1.1 Backend — Tracker owns only the Applications tab

```
apps/api/app/modules/tracker/
├── __init__.py
├── routes.py      # GET (paginated), POST, PUT /{id}, DELETE /{id} — all rate-limited
├── schemas.py      # ApplicationIn — length bounds + status Literal
├── models.py       # JobApplication (job_applications table) — CheckConstraints mirror schema
└── service.py      # list_applications (unpaginated OR keyset-paginated), CRUD orchestration
```

The other three tabs call straight through to their owning modules'
existing routers — `app/modules/startup_hunt/`, `app/modules/
startup_scout/`, `app/modules/job_search/` — unchanged by Tracker beyond
the shared `shared/repository.py::list_page` addition (§2.2) and the three
session tables' new `source_job_application_id` column (§2.3).

### 1.2 Frontend — one file, four tabs, two render paths each

```
apps/web/app/(dashboard)/tracker/page.tsx   (~2,100 lines)
├── usePaginatedList<T>(baseUrl)            # generic cursor-pagination hook, local state
├── LoadMoreRow                              # shared "Load more" button
├── renderApplicationCard / renderLeadCard /
│   renderScoutCard / renderJobSearchCard    # mobile card renderers, one per tab
├── renderContactsPanelBody                  # shared between Scout's desktop <tr> and
│                                             # mobile card - same contact-list markup either way
└── founderSearchUrl(companyName)            # client-only "Find Founders" link builder,
                                              # zero backend calls, isolated from startup_scout
```

---

## 2. Core Workflows

### 2.1 Add/Edit Application (`routes.py::create_application` / `update_application`)

1. Daily quota (`rate_limit_tracker_create_per_day`, create only) then
   burst window (every write, including delete).
2. `ApplicationIn` validates `company`/`role` (≤200 chars, required),
   `notes` (≤3,000, optional), `status` (fixed `Literal`), `applied_at`/
   `follow_up_date` (ISO date format).
3. `TrackerRepository(db).create(...)` / `.update(...)` — generic
   `UserScopedRepository` methods, no Tracker-specific query logic beyond
   field validation.
4. On success, the frontend calls `reloadApplications()` (re-fetches page
   1 of the paginated list) rather than `queryClient.invalidateQueries` —
   see §2.2 for why plain react-query cache invalidation doesn't fit here.

### 2.2 Cursor Pagination (`usePaginatedList`, `shared/repository.py::list_page`)

**Frontend**: `usePaginatedList<T>(baseUrl)` is local `useState`, not a
react-query cache entry, for a specific reason: `queryKeys.tracker` /
`startupHuntOpportunities` / `startupScoutCompanies` / `jobSearchApplications`
are shared cache keys with Dashboard, Startup Hunt's own page, Startup
Scout's own page, and Recent Job Search — all of which call the same
endpoints expecting the *full* array. If Tracker cached only "the first 50
loaded so far" under those same keys, it would corrupt what those other
pages read on their own next render. Each tab's hook does its own
`apiFetch(url + '?limit=50[&cursor=...]')`, reads `next_cursor` from the
`X-Next-Cursor` response header, and appends to local `items` state on
"Load more."

**Backend**: `UserScopedRepository.list_page(user_id, *, limit, cursor)`
— ordered by `(created_at, id) DESC`, `id` breaking ties so the cursor is
unambiguous even when two rows share a timestamp. A cursor is
`"<created_at.isoformat()>_<id>"`; a malformed one (tampered param, stale
bookmarked link) is treated as "start from the top," not a 500. Each of
the four route handlers accepts `limit`/`cursor` as optional `Query`
params and only engages this path when `limit` is explicitly given —
omitting it preserves the exact prior unbounded `list()` call, so every
other consumer of these endpoints is unaffected.

```python
# shared/repository.py — the keyset query shape
stmt = self._scoped(select(self.model), user_id)          # user isolation FIRST
if cursor:
    stmt = stmt.where(tuple_(self.model.created_at, self.model.id) < tuple_(cursor_created_at, cursor_id))
stmt = stmt.order_by(self.model.created_at.desc(), self.model.id.desc()).limit(limit + 1)
```

The `limit + 1` trick (fetch one extra row) is what lets a single query
answer both "here's the page" and "is there a next page" without a
separate `COUNT(*)`.

### 2.3 My Docs Cross-Linkage (`source_job_application_id`)

Mirrors the pre-existing `source_opportunity_id`/`source_application_id`
pattern exactly, on all three session tables (`tailoring_sessions`,
`cover_letter_sessions`, `interview_prep_sessions`):

1. Tracker's "Use with tools" menu (Applications tab only — the other two
   linkages already existed for Leads/Job Search) passes
   `?job_application_id={app.id}` to Resume Tailor/Cover Letter/Interview
   Prep.
2. Each tool's generate endpoint re-verifies ownership
   (`verify_job_application_ownership`, querying `job_applications` by id
   + the caller's `user_id` — never trusts the client-supplied id alone)
   before storing it as `source_job_application_id`.
3. My Docs' `groupKeyFor()` checks all three linkage fields; two or more
   documents sharing any one of them render as a single `JobGroupCard`.
4. Tracker's own "View docs →" link (`docCountFor`, a memoized
   `Map<"field:id", count>` built once per render from the three session
   lists) shows a per-row count and deep-links to
   `/my-docs?q=<company>+<role>` — a text search, not an id-based
   lookup, so it works identically for a doc whose source row was later
   renamed.

### 2.4 Mobile Card Rendering

Each tab's card renderer (`renderApplicationCard` etc.) is a plain
function, not a separate `<Component/>` — called directly inside
`.map()`, closing over the same handlers/state as the desktop table
(`openEdit`, `updateApplicationStatus`, `deleteApp`, `docCountFor`, …) with
zero prop-drilling. Both the desktop `<Table>` (`hidden sm:block`) and the
mobile card list (`sm:hidden`) are always mounted; CSS alone decides which
renders, so there's no `useEffect`/resize-listener/hydration-mismatch risk
— the tradeoff is that every tab's JSX now exists twice (table row +
card), a real but accepted maintenance cost (see `production_hardening_
playbook.md`'s "What's explicitly not done").

Scout's contacts panel specifically is factored into one shared
`renderContactsPanelBody(company, contacts, loading, canCrawl)` called by
*both* the desktop `<tr>`'s expand row and the mobile card's expand
section — the one piece of this tab's UI that would otherwise have
drifted out of sync between the two layouts.

---

## 3. Design Notes

### 3.1 Why `start_crawl` Commits Synchronously, Not Inside the Job

**Found**: `start_crawl`'s "already crawling" guard checked a status that
was only flipped to `crawling` *inside* the background job — i.e., after
the HTTP response that triggered the enqueue had already gone out. Two
rapid clicks (or two browser tabs) could both read `pending` and both
pass the guard before either job had started.

**Fix**: the status flip and its `db.commit()` now happen inside
`start_crawl` itself, synchronously, before the route even enqueues the
job. See `docs/startup_scout/production_hardening_notes.md`'s "Phase B
hardening" section for the full writeup (this bug lives in
`startup_scout`, reached from Tracker's Scout tab, not in Tracker's own
backend).

### 3.2 Why the Notes-Viewing Dialog Needed a Scoped `overflow-y-auto`

**Found**: `ApplicationIn.notes` allows up to 3,000 characters, but the
shared `Dialog`/`DialogContent` component has no built-in max-height or
scroll handling — a long note would grow the dialog past the viewport
with no way to see the rest.

**Fix**: `max-h-[50vh] overflow-y-auto scrollbar-thin` on just the note
`<p>`, scoped to this one dialog instance (not the shared `Dialog`
component — no reason every dialog in the app should get this).

### 3.3 Why `docCountFor` Became a Precomputed Map, Not Per-Call Filters

**Found**: `docCountFor(id, field)` ran up to three `.filter()` passes
(one per session table) on every call, and it's called twice per
row-with-linked-docs (once for the `> 0` check, once for the displayed
count) across three tabs' worth of rows — cost scaled with
rows-on-screen × sessions, recomputed from scratch on every render.

**Fix**: a single `Map<"field:sourceId", count>` built once per render in
one pass over the three session arrays; `docCountFor` is now an `O(1)`
lookup. Not performance-critical at this app's actual scale (tens of
rows, tens of sessions) — fixed because the redundant-scan pattern was
easy to eliminate cleanly, not because it was observed to be slow.

---

## 4. Resilience & Fallback Contracts

| Failure | Behavior |
| :--- | :--- |
| Redis down (rate limiting) | Fails open on both the daily-quota and burst checks, consistent with every other limiter in this codebase. |
| Malformed/stale pagination cursor | Treated as "start from the top" (first page), not a 500. |
| `PUT`/`DELETE` on an application that doesn't exist or isn't owned by the caller | `404` — `UserScopedRepository`'s `user_id` scoping makes a mismatched id and a nonexistent id indistinguishable from the outside, by design. |
| A linked tool's session has a `source_job_application_id` whose row was since deleted | `ON DELETE SET NULL` — the document is kept (still worth having even if its source application is gone), just un-grouped. |
| Leads/Scout/Job Search tab's underlying module is degraded | Out of Tracker's control/scope — see that module's own hardening playbook (`docs/startup_hunt/`, `docs/startup_scout/`, `docs/recent_job_search/`). |
