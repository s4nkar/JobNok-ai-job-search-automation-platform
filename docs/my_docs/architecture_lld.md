# My Docs: Low-Level Design (LLD)

**Document Version:** 1.0.0
**Status:** Approved for Production
**Target Audience:** Backend Engineers, Frontend Engineers

---

## 1. Frontend: Fetch, Normalize, Group

`apps/web/app/(dashboard)/my-docs/page.tsx` runs three independent
`useQuery` calls (`queryKeys.tailoringSessions`, `.coverLetterSessions`,
`.interviewPrepSessions`), each hitting its module's own `GET .../sessions`
endpoint. Every response shape differs (see §2's field table) — each gets
normalized into one common `DocRow` via `toResumeDocRow` / `toCoverLetterDocRow`
/ `toInterviewPrepDocRow` before anything else happens:

```ts
interface DocRow {
  id: string
  kind: 'resume' | 'cover_letter' | 'interview_prep'
  label: string
  isAiMatched: boolean
  meta: string
  matchScore: number | null
  createdAt: string
  isDraft: boolean
  previewHtml: string | null
  openHref: string
  sourceOpportunityId: string | null
  sourceApplicationId: string | null
  sourceJobApplicationId: string | null
}
```

### 1.1 Grouping (`buildGridItems`)

```ts
function groupKeyFor(row: DocRow): string | null {
  if (row.sourceOpportunityId) return `opp:${row.sourceOpportunityId}`
  if (row.sourceApplicationId) return `app:${row.sourceApplicationId}`
  if (row.sourceJobApplicationId) return `job:${row.sourceJobApplicationId}`
  return null
}
```

Rows are bucketed by this key; a bucket with **2+ rows** becomes a
`JobGroupCard`, everything else (including a bucket of exactly 1, and
every row with no linkage at all) renders as a standalone `DocCard`. This
is an O(n) pass over the full unbounded result set, re-run on every
query refetch — see `production_hardening_playbook.md` §4 for the scaling
characteristics this implies.

### 1.2 Card Rendering

Both `DocCard` and `JobGroupCard` use the same fixed-height panel
(`PREVIEW_PEEK_HEIGHT = 128px`) regardless of document kind, so a resume
(real HTML thumbnail via `ScaledResumeThumb`), a cover letter, and an
interview kit all occupy the same footprint in the grid. Cover letters
and interview kits have no rendered-HTML equivalent to preview (they're
plain text/JSON, not a styled template) — their panel shows a centered
icon + label instead (`KIND_META`), using the same brand-indigo accent as
every other page-header icon in the app rather than a per-kind color,
and a thin stroke (`strokeWidth={1.25}`, `text-slate-500`) to stay visually
quiet next to an actual resume thumbnail. `JobGroupCard`'s collage splits
this same panel into one pane per document, in a fixed `KIND_ORDER`
(resume, cover letter, interview kit) regardless of creation order, each
independently clickable straight to that document, separated by a
`divide-x divide-slate-200` vertical rule and a `hover:bg-slate-50` tint
per pane so each section reads as separately clickable.

### 1.3 Reopen-Locks-the-Form (Cover Letter / Interview Prep)

Both pages read a `session_id` query param. On load, if present, they
fetch the full session detail, prefill the form, **and set `isLocked =
true`**. While locked: the form's fields sit inside a `<fieldset
disabled={isLocked}>` (HTML-native, disables every contained control in
one line) and the real submit button is swapped for a `type="button"`
"Edit & Regenerate" that only flips `isLocked` back to `false` — it does
not resubmit anything itself. A small banner ("Viewing your saved
letter/kit") explains why the form is non-interactive. This is pure
client-side state; nothing server-side changes based on lock state — the
backend has no concept of "locked," it's purely a frontend guard against
an accidental resubmit (see `architecture_hld.md` §3.3 for why this
exists at all).

One frontend-only wrinkle in Interview Prep: reopening a session also
populates `trackerApp` (company/role), which independently feeds a
"Pre-filled from your tracker" banner used by the *tracker-link* entry
path. Reopening isn't that path, so that banner is explicitly suppressed
for the whole visit (`trackerApp && !reopenSessionId`) while `trackerApp`
itself stays populated (it's still needed to keep `knownCompany`/
`knownRole` accurate if the user unlocks and regenerates).

---

## 2. Backend: Three Modules, One Shape, Real Drift

| Field | resume_tailor `SessionSummary` | cover_letter `CoverLetterSessionSummary` | interview_prep `InterviewPrepSessionSummary` |
| :--- | :---: | :---: | :---: |
| `id`, `title`, `display_label`, `created_at`, `source_*_id` ×3 | ✅ | ✅ | ✅ |
| `is_ai_matched` | ✅ | — | — |
| `template_id` | ✅ | — | — |
| `match_score` | ✅ | — | — |
| `is_draft` | ✅ | — | — |
| `preview_html` | ✅ | — | — |
| `question_count` | — | — | ✅ |

Only the first six fields are common to all three — the rest reflect
genuinely different domains (a resume has a template/match score/draft
state; an interview kit has a question count) and are **not** drift to
reconcile. What *is* real drift, found during the production audit:

- **`display_label` fallback chains differ in shape, not just content.**
  `resume_tailor`: title → linked opportunity/application (batch DB
  lookup) → AI-parsed `prose.target_role`/`target_company` (flagged
  `is_ai_matched=True`) → `"Standalone Resume"`. `cover_letter`: title →
  `"{role} at {company}"` only — company/role are always literal form
  fields here, so there's no opportunity lookup or AI-matched ambiguity.
  `interview_prep`: title → `"{role} at {company}"` (only if **both** are
  set) → AI-inferred `role_assessment.role_family` → `"Interview Prep
  Kit"` — a three-tier fallback that *does* have an AI-derived case
  (`role_family`) but, unlike `resume_tailor`, carries no `is_ai_matched`
  flag to tell the frontend so. Net effect: the sparkle "AI-detected"
  icon on My Docs only ever appears on resume cards, never on an
  interview kit that fell back to the same kind of AI-derived label.
  Documented here as a known, low-priority cosmetic gap — not fixed in
  this pass (would need a new schema field + service change + frontend
  change for a sparkle icon, not proportional to the inconsistency).
- **Generation single-flight lock scope differed until this audit.**
  `resume_tailor` keys its lock per-job
  (`tailor_job:{user_id}:{job_id}:lock`), only taken when a job id is
  present at all — two different jobs' tailoring can run in parallel.
  `cover_letter`/`interview_prep` previously keyed per-user
  unconditionally (`cover_letter_gen:{user_id}:lock`), serializing *all*
  of a user's generations regardless of job. Fixed in this audit to
  match `resume_tailor`'s per-job scoping when a linkage id is present,
  falling back to per-user only for a genuinely ad-hoc generation. See
  `production_hardening_playbook.md` §2.
- **Detail endpoint file placement differs** (`resume_tailor`'s
  `GET /tailor/{id}` lives in `routes.py` alongside generate/editor/pdf;
  `cover_letter`/`interview_prep` put list+detail+rename together in
  their own `sessions_routes.py`). Purely organizational, no behavioral
  difference.

### 2.1 `resolve_session` — the Auto-Persist Upsert

`cover_letter/service.py` and `interview_prep/service.py` each implement
the same resolution order, independently:

1. If a job linkage id is present **and** ownership-verified
   (`verify_opportunity_ownership` / `verify_application_ownership` /
   `verify_job_application_ownership`, checked in that priority order),
   look up the existing session already linked to that job
   (`get_by_source`) — "one saved document per job."
2. Else, if a `session_id` was passed (continuing the same ad-hoc browser
   visit), look that up by id instead.
3. If neither resolves to a row, create a new one.

```python
# cover_letter/service.py::resolve_session (interview_prep's is structurally identical)
if existing is not None:
    session = await repo.update(user_id, str(existing.id), ...)
else:
    try:
        async with db.begin_nested():
            session = await repo.create_session(user_id, ..., source_opportunity_id=..., ...)
    except IntegrityError:
        # Lost a race - a concurrent request for the same job won the
        # INSERT first and tripped the partial unique index (models.py).
        existing = await repo.get_by_source(user_id, ...)
        if existing is None:
            raise
        session = await repo.update(user_id, str(existing.id), ...)
```

The `try`/`except IntegrityError` block (added in this audit) is the only
thing standing between "two concurrent requests for the same job" and
two duplicate rows — see `production_hardening_playbook.md` §2 for why
this was needed even with the Redis lock already in place. `db.begin_nested()`
opens a SAVEPOINT so a failed INSERT only rolls back that one statement,
not the whole request's transaction — the subsequent `get_by_source` +
`update` fallback still runs inside the same outer session/transaction.

---

## 3. Known, Accepted Gaps (Not Fixed in This Pass)

- **No DB-level pagination on any of the three list endpoints.** Each
  calls plain `UserScopedRepository.list()` (unbounded), despite the
  shared repo already exposing a fully-built keyset-cursor
  `list_page()` (the same method Tracker's four endpoints use). Not
  wired up here because My Docs groups across all three lists
  client-side — paginating each list independently would either break
  grouping (a resume on page 1 might pair with a cover letter on page 3)
  or require a server-side "grouped item" pagination redesign, which is
  a bigger lift than today's actual growth rate justifies (every
  contributing action — a tailor, a save, a generation — is already
  rate-limited elsewhere; this isn't a scraper-fed table like Tracker's
  Scout tab that can grow by hundreds of rows in a single crawl).
  Documented as a scaling characteristic to revisit if evidence of real
  usage at that scale appears — see `production_hardening_playbook.md`
  §4 for the concrete behavior at hypothetical scale.
- **`resume_tailor`'s list endpoint does real per-row work** (a batch
  `SELECT ... IN` for linked opportunities/applications, plus a full
  Jinja HTML render for every session with a saved draft) — acceptable
  today, a candidate for a cached-rendered-HTML-by-draft-version
  optimization if list latency is ever observed to be a problem.
- **No automated test coverage for anything DB-touching** (ownership
  scoping, the race-condition fix, FK `ON DELETE SET NULL` behavior,
  pagination). This codebase has no DB-fixture test infrastructure at
  all — a pre-existing, project-wide limitation (see Tracker's own
  playbook for the same note), not something specific to My Docs. What
  *is* testable without a DB (Pydantic schema boundaries, pure
  display-label functions) already has coverage; see
  `production_hardening_playbook.md` §5.
