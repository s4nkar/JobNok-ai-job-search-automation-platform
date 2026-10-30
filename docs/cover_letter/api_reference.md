# Cover Letter: API Reference

**Base URL**: `/api/ai`
**Authentication**: Bearer JWT (Clerk) in `Authorization` header, resolved to `user_id` on every request.

---

## 1. Generate a Cover Letter (Streamed)

### `POST /api/ai/cover-letter`

Streams a tailored cover letter as plain text chunks — **not** real Server-Sent Events (no `data:`-prefixed frames), just raw text over a chunked response. The frontend reads it via `response.body.getReader()`.

#### Request (`application/json`)
| Field | Type | Required | Max Length | Description |
| :--- | :--- | :--- | :--- | :--- |
| `company` | string | Yes | 200 | Company name. May originate from a scraped Startup Hunt opportunity, not just user typing. |
| `role` | string | Yes | 200 | Role/position title. |
| `selling_points` | string | Yes (min 20) | 3,000 | The candidate's pitch — pre-fillable from `profiles.key_selling_points`. |
| `resume_text` | string | No | 8,000 | Optional resume excerpt for extra grounding context. |
| `opportunity_id` | string | No | - | A Startup Hunt opportunity to auto-save this generation against (see §3). Ownership is re-verified server-side. |
| `job_search_application_id` | string | No | - | Same, for a tracked job application. |
| `session_id` | string | No | - | An ad-hoc session (no job link) from earlier in this same browser visit, to update in place instead of creating a new one — see §3. |

```json
{
  "company": "Google",
  "role": "AI Engineer",
  "selling_points": "End-to-end AI engineering — you build complete systems, not just models...",
  "resume_text": null
}
```

#### Response (`200 OK`, `text/plain`, streamed)
Raw text chunks, concatenated client-side into the full letter. On a mid-stream failure (provider exhausted, network error), a bracketed notice is appended instead of a silent cutoff:
```
[Generation interrupted - the AI service is temporarily unavailable. Please try again in a moment.]
```
The response status is still `200` in this case — ASGI commits to the status line before the body iterator is first awaited, so a failure partway through streaming can't be turned into a proper error code. The frontend treats the bracketed notice as user-visible text in the editable textarea (deletable like anything else).

An `X-Session-Id` response header carries the id of the `CoverLetterSession` row this generation was auto-saved into (see §3) — set before streaming starts, since the streamed body has no room for a JSON field. The frontend reads it immediately and holds it for the rest of the visit.

#### Error Responses
- `422 Unprocessable Entity`: a field fails validation (missing, too short, too long).
- `429 Too Many Requests`: daily quota (`rate_limit_cover_letter_per_day`, default 5) or burst window exceeded.

---

## 2. Export the Letter as PDF

### `POST /api/ai/cover-letter/pdf`

Renders exactly the text the client sends as a one-page PDF. No AI call, no content changes (no auto-inserted salutation or signature) — pure typography.

#### Request (`application/json`)
| Field | Type | Required | Max Length | Description |
| :--- | :--- | :--- | :--- | :--- |
| `content` | string | Yes | 5,000 | The letter text currently shown in the frontend's editable textarea. |

```json
{ "content": "When Google announced its new AI-engineered search initiative..." }
```

#### Response (`200 OK`, `application/pdf`)
Raw PDF bytes with `Content-Disposition: attachment; filename="cover-letter.pdf"`. The frontend fetches this as a blob and builds its own download link with a company/role-based filename rather than relying on the server-side header's generic name.

#### Error Responses
- `422 Unprocessable Entity`: `content` missing, empty, or over 5,000 characters.
- `429 Too Many Requests`: daily quota (`rate_limit_cover_letter_pdf_per_day`, default 20, separate from the generation quota) or burst window exceeded.

---

## 3. Saved Letters (My Docs) — Auto-Save, List, Get, Rename

There is no `POST /save` — persistence is folded into `POST /api/ai/cover-letter` itself (see §1's `X-Session-Id` header). A generation auto-saves into a `cover_letter_sessions` row rather than requiring an explicit click: this avoids losing a generated letter (and paying for a full AI regeneration) just because the user forgot to click Save.

**Upsert rule — "only one saved letter per job":** when `opportunity_id`/`job_search_application_id` is given, the backend looks up any existing session already linked to that job for this user and overwrites it in place instead of creating a duplicate, regardless of browser visit. With no job link, `session_id` (held client-side from a prior response's `X-Session-Id`) lets the frontend keep updating the same ad-hoc row across regenerations within one visit; a fresh page visit with no `session_id` starts a new row.

### `GET /api/ai/cover-letter/sessions`

Lists every saved letter for "My Docs", most recent first. Response: `{ "sessions": CoverLetterSessionSummary[] }`, each with `id, title, display_label, created_at, source_opportunity_id, source_application_id`.

### `GET /api/ai/cover-letter/sessions/{id}`

Fetches one saved letter in full (`CoverLetterSessionDetail`) - used to reopen a saved letter in the generator page via `?session_id=`, which also re-arms that id for the upsert rule above.

```json
{
  "id": "...", "title": null, "company": "Google", "role": "AI Engineer",
  "selling_points": "...", "resume_text": null, "content": "...",
  "created_at": "...", "source_opportunity_id": null, "source_application_id": null
}
```

### `PATCH /api/ai/cover-letter/sessions/{id}/title`

Body: `{ "title": "..." }` (max 200 chars). Response: `{ "title": "..." }`.

#### Error Responses (all three endpoints)
- `404 Not Found`: session doesn't exist or isn't owned by the caller.
- `429 Too Many Requests`: burst window exceeded (no daily quota - these aren't AI-costed).

---

## 4. Related Endpoints (Owned by Other Modules)

Cover Letter's "reuse your selling points" feature reads/writes through the Profile module, not its own:

- `GET /api/profile` — includes `key_selling_points` in the response; the Cover Letter page fetches this to pre-fill `selling_points` on load.
- `PUT /api/profile` — the Profile page's "Default Selling Points" field writes here (`key_selling_points`, max 3,000 chars, enforced in `profile/service.py` since that module has no Pydantic request schema).

See `docs/cover_letter/data_flow_and_schema.md` §1.2 for the full field contract.
