# My Docs: API Reference

**Document Version:** 1.0.0
**Status:** Approved for Production

All endpoints require a valid Clerk JWT (`Authorization: Bearer ...`) and
are scoped to the authenticated user via `UserScopedRepository` — a
session id belonging to another user returns `404`, not `403`. Every
endpoint below additionally has a Redis burst-window check
(`rate_limit_burst_limit` / `rate_limit_burst_window_seconds`); it fails
**open** (allows the request) if Redis is unreachable, same as every
other rate limiter in this codebase.

---

## Resume Tailor (`resume_tailor`)

### `GET /api/ai/tailor/sessions`
Returns every tailoring session for the user, most recent first —
`resume_tailor/sessions_routes.py`.

**Burst bucket**: `resume_tailor_sessions_list`

**Response** (`SessionListResponse`):
```json
{
  "sessions": [{
    "id": "uuid", "title": "string|null", "display_label": "string",
    "is_ai_matched": "bool", "template_id": "string|null", "match_score": "int",
    "created_at": "iso8601", "is_draft": "bool", "preview_html": "string|null",
    "source_opportunity_id": "uuid|null", "source_application_id": "uuid|null",
    "source_job_application_id": "uuid|null"
  }]
}
```

### `GET /api/ai/tailor/{session_id}`
Full session detail, used when reopening into the **editor** (not the
generation form — see `architecture_hld.md` §3.3). `resume_tailor/routes.py`.

**Burst bucket**: `resume_tailor_sessions_detail` (added in this audit —
previously unprotected).

**Errors**: `404` if the session doesn't exist or isn't owned by the
caller.

### `PATCH /api/ai/tailor/{session_id}/title`
Rename. Body: `{"title": "string, max 200 chars"}`. Rejects an
all-whitespace title with `422` after server-side `.strip()`.

**Burst bucket**: `resume_tailor_title`

---

## Cover Letter (`cover_letter`)

### `GET /api/ai/cover-letter/sessions`
`cover_letter/sessions_routes.py`. **Burst bucket**:
`cover_letter_sessions_list`.

**Response** (`CoverLetterSessionListResponse`):
```json
{
  "sessions": [{
    "id": "uuid", "title": "string|null", "display_label": "string",
    "created_at": "iso8601",
    "source_opportunity_id": "uuid|null", "source_application_id": "uuid|null",
    "source_job_application_id": "uuid|null"
  }]
}
```

### `GET /api/ai/cover-letter/sessions/{session_id}`
Full detail (company, role, selling_points, resume_text, content), used
when reopening into the generation page in locked/view mode.

**Burst bucket**: `cover_letter_sessions_detail` (added in this audit).

### `PATCH /api/ai/cover-letter/sessions/{session_id}/title`
Same shape/behavior as resume_tailor's rename. **Burst bucket**:
`cover_letter_title`.

### No `POST /save` — persistence is implicit
There is no explicit save endpoint. `POST /api/ai/cover-letter` (the
generation endpoint) auto-persists via `resolve_session()` *before* the
AI stream starts, and hands the row's id back via an `X-Session-Id`
response header (the endpoint streams plain text, so it can't return the
id in a JSON body). A job-linked generation upserts into that job's
single existing row; an ad-hoc generation (no job link) creates a new row
per browser visit, continuing to update that same row across regenerates
within the visit via a client-held `session_id`.

**Race-condition note**: concurrent requests for the same job are
serialized by a per-job (or per-user, if no job link) Redis single-flight
lock (`cover_letter_gen:{user_id}:{job_id}:lock`) — but that lock fails
open if Redis is down. A DB-level partial unique index on
`(user_id, source_opportunity_id)` (and the other two linkage columns) is
the real backstop; `resolve_session` catches the resulting
`IntegrityError` and falls back to updating the row that won the race
rather than erroring the request. See `production_hardening_playbook.md`
§2.

---

## Interview Prep (`interview_prep`)

### `GET /api/ai/interview/sessions`
`interview_prep/sessions_routes.py`. **Burst bucket**:
`interview_sessions_list`.

**Response** (`InterviewPrepSessionListResponse`):
```json
{
  "sessions": [{
    "id": "uuid", "title": "string|null", "display_label": "string",
    "question_count": "int", "created_at": "iso8601",
    "source_opportunity_id": "uuid|null", "source_application_id": "uuid|null",
    "source_job_application_id": "uuid|null"
  }]
}
```

### `GET /api/ai/interview/sessions/{session_id}`
Full detail (job_description, company, role, the validated `result`
JSONB blob). **Burst bucket**: `interview_sessions_detail` (added in this
audit).

### `PATCH /api/ai/interview/sessions/{session_id}/title`
Same shape/behavior as the other two. **Burst bucket**: `interview_title`.

### No `POST /save` — same implicit-persist pattern as Cover Letter
`POST /api/ai/interview` auto-persists via its own `resolve_session()`
after the (non-streaming) generation completes. Same race-condition note
and same DB-level partial-unique-index backstop as Cover Letter above.

---

## Common Error Shape

A `422` from any `PATCH .../title` call follows FastAPI's standard
validation-error body (`{"detail": [{"type", "loc", "msg", ...}]}`) for a
schema failure (e.g. title over 200 chars), or a plain string `detail`
for the explicit "Title cannot be empty" check. The frontend's shared
`describeApiError()` (`apps/web/lib/api.ts`) parses both shapes.
