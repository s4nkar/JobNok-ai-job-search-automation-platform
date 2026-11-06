# Tracker: API Reference

**Base URL (Applications tab, Tracker-owned)**: `/api/tracker`
**Authentication**: Bearer JWT Token in `Authorization` header, every endpoint.

The Leads, Scout, and Job Search tabs call their owning modules' own APIs
directly — `/api/startup-hunt`, `/api/startup-scout`, `/api/job-search`
respectively. Those endpoints are documented in full in each module's own
`api_reference.md`; this document covers only what's specific to Tracker:
the Applications tab's own endpoints, and the cursor-pagination contract
all four tabs' list endpoints now share.

---

## 1. Applications (Tracker-owned)

### `GET /api/tracker`
Lists the current user's manually-tracked applications, newest first.

**Query params** (both optional — see §3 for the contract):
- `limit` (1–200): page size. Omit for the original unbounded response.
- `cursor`: opaque pagination token from a previous response's
  `X-Next-Cursor` header.

**Response**: a bare JSON array of application objects (same shape
whether paginated or not — pagination state lives entirely in the
response header, never the body).

### `POST /api/tracker`
Creates a new tracked application. Rate-limited by
`rate_limit_tracker_create_per_day` (daily quota) plus the burst-window
guard every write endpoint here has.

**Request body**:
```json
{
  "company": "Acme Corp",
  "role": "Software Engineer",
  "applied_at": "2026-11-01",
  "status": "Applied",
  "follow_up_date": "2026-12-01",
  "salary_min": 80000,
  "salary_max": 120000,
  "notes": "Referred by a friend on the team."
}
```
- `company`/`role`: required, 1–200 chars.
- `status`: one of `Applied`, `Phone Screen`, `Interview`, `Offer`,
  `Rejected`, `Withdrawn`.
- `applied_at`/`follow_up_date`: ISO 8601 date (`YYYY-MM-DD`).
- `notes`: optional, ≤3,000 chars.

### `PUT /api/tracker/{app_id}`
Full update — same body shape as `POST`. `404` if the id doesn't exist or
isn't owned by the caller.

### `DELETE /api/tracker/{app_id}`
`204` on success, `404` if not found/not owned.

---

## 2. Cross-Module Linkage (read by Resume Tailor / Cover Letter / Interview Prep)

These three tools accept an optional `job_application_id` (alongside the
pre-existing `opportunity_id`/`job_search_application_id`) when generating
from a tracked Application row, so the resulting document can be grouped
with others for the same job in My Docs:

- `POST /api/ai/tailor` (form field `job_application_id`)
- `POST /api/ai/cover-letter` (JSON field `job_application_id`)
- `POST /api/ai/interview` (JSON field `job_application_id`)

Each tool re-verifies that the id belongs to the caller before storing it
— see `data_flow_and_schema.md` §1.2. Documented in full in each tool's
own `api_reference.md`; noted here because the *trigger* for sending it
is Tracker's own "Use with tools" menu.

---

## 3. Cursor Pagination Contract (shared by all four tabs' list endpoints)

Added to `GET /api/tracker`, `GET /api/startup-hunt/opportunities`,
`GET /api/startup-scout/companies`, and `GET /api/job-search/
applications` identically:

| Param | Required | Notes |
| :--- | :--- | :--- |
| `limit` | No | `1`–`200`. Enables pagination when present. |
| `cursor` | No | Opaque token, only meaningful alongside `limit`. |

**Response header** `X-Next-Cursor`: present only when more rows exist
beyond this page. Absent (not an empty string) once the last page is
reached — check for the header's presence, not its value, to know
whether to show a "Load more" control.

**Backward compatibility**: omitting both params returns the exact same
unbounded array every one of these endpoints always returned — Dashboard,
Startup Hunt's own page, Startup Scout's own page, and Recent Job Search
all still call these URLs with neither param and are unaffected.

`job_search/applications` is the one exception with pre-existing
`offset`-based pagination (`limit`/`offset`) from before this work — passing
`cursor` takes priority over `offset` when both are somehow present; a
genuinely nonzero `offset` (nothing currently sends one) falls back to the
original `OFFSET` behavior with no `X-Next-Cursor` header, since an
arbitrary offset has no well-defined keyset anchor to resume from.
