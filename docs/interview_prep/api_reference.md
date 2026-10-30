# Interview Prep: API Reference

**Base URL**: `/api/ai`
**Authentication**: Bearer JWT (Clerk) in `Authorization` header, resolved to `user_id` on every request.

---

## 1. Generate an Interview Prep Kit

### `POST /api/ai/interview`

Auto-saves on every successful generation (see §3) — no separate save step.

#### Request (`application/json`)
| Field | Type | Required | Max Length | Description |
| :--- | :--- | :--- | :--- | :--- |
| `job_description` | string | Yes (min 20) | 12,000 | The job description to analyze. |
| `company` | string | No | 200 | Trusted company name from an already-known Startup Hunt lead or tracked application. Takes precedence over anything the model might guess from the JD text. |
| `role` | string | No | 200 | Same, for role/title. |
| `opportunity_id` | string | No | - | A Startup Hunt opportunity to auto-save this generation against. Ownership re-verified server-side. |
| `job_search_application_id` | string | No | - | Same, for a tracked job application. |
| `session_id` | string | No | - | An ad-hoc session (no job link) from earlier in this same browser visit, to update in place instead of creating a new one. |

```json
{
  "job_description": "About the job\nAre you an AI Engineer looking for...",
  "company": null,
  "role": null
}
```

#### Response (`200 OK`)
```json
{
  "role_assessment": {
    "seniority": "mid",
    "role_family": "AI/ML Engineer",
    "likely_rounds": ["Recruiter screen", "Technical phone screen", "System design round", "Hiring manager interview"],
    "company_context": null,
    "dsa_likely": true,
    "system_design_likely": true
  },
  "questions": [
    { "question": "...", "framework": "STAR", "answer_framework": "...", "tips": ["...", "..."] }
  ],
  "dsa_questions": [
    { "question": "...", "approach": "..." }
  ],
  "system_design_questions": [
    { "question": "...", "approach": "..." }
  ],
  "session_id": "..."
}
```
`questions` always has 10 items. `dsa_questions`/`system_design_questions` are empty arrays when `role_assessment.dsa_likely`/`system_design_likely` is `false` — not every role gets these. `company_context` is `null` when no specific, identifiable company could be named without fabricating one.

#### Error Responses
- `422 Unprocessable Entity`: a field fails validation (missing, too short, too long).
- `429 Too Many Requests`: daily quota (`rate_limit_interview_per_day`, default 10), burst window, or a generation already in progress for this user (single-flight lock — see `architecture_lld.md` §2.1).
- `500 Internal Server Error`: the LLM response couldn't be parsed as JSON.
- `503 Service Unavailable`: every AI provider in the fallback chain is exhausted.

---

## 2. Regenerate One Question's Answer

### `POST /api/ai/interview/regenerate`

#### Request (`application/json`)
| Field | Type | Required | Max Length | Description |
| :--- | :--- | :--- | :--- | :--- |
| `job_description` | string | Yes (min 20) | 12,000 | Same JD as the original generation (truncated to 1,500 chars server-side for this cheaper call). |
| `question` | string | Yes | 500 | The question text to regenerate an answer for. |
| `session_id` | string | No | - | The saved kit this question belongs to — when given with `question_index`, the regenerated answer is written back into that kit. |
| `question_index` | integer | No | - | The 0-based index of this question within the saved kit's `questions` array. |

```json
{ "job_description": "...", "question": "Tell me about a time you took an AI model to production.", "session_id": "...", "question_index": 2 }
```

#### Response (`200 OK`)
```json
{ "answer_framework": "...", "tips": ["...", "..."] }
```
Note: `question`/`framework` are not part of the response — only the two fields that actually change.

#### Error Responses
- `422 Unprocessable Entity`: a field fails validation.
- `429 Too Many Requests`: daily quota (`rate_limit_interview_regenerate_per_day`, default 30 — separate bucket from generation), burst window, or this exact question is already being regenerated (single-flight lock, scoped per `session_id`+`question_index`).
- `500 Internal Server Error` / `503 Service Unavailable`: same as §1.

---

## 3. Saved Kits (My Docs) — Auto-Save, List, Get, Rename

There is no `POST /save` — persistence is folded into `POST /api/ai/interview` itself (see §1's `session_id` response field).

**Upsert rule — "only one saved kit per job":** when `opportunity_id`/`job_search_application_id` is given, the backend looks up any existing session already linked to that job for this user and overwrites it in place instead of creating a duplicate, regardless of browser visit. With no job link, `session_id` (held client-side from a prior response) lets the frontend keep updating the same ad-hoc row across generations within one visit; a fresh page visit with no `session_id` starts a new row.

### `GET /api/ai/interview/sessions`

Lists every saved kit for "My Docs", most recent first. Response: `{ "sessions": InterviewPrepSessionSummary[] }`, each with `id, title, display_label, question_count, created_at, source_opportunity_id, source_application_id`.

### `GET /api/ai/interview/sessions/{id}`

Fetches one saved kit in full (`InterviewPrepSessionDetail`) - used to reopen a saved kit in the generator page via `?session_id=`, which also re-arms that id for the upsert rule above.

```json
{
  "id": "...", "title": null, "job_description": "...", "company": null, "role": null,
  "result": { "role_assessment": {...}, "questions": [...], "dsa_questions": [...], "system_design_questions": [...] },
  "created_at": "...", "source_opportunity_id": null, "source_application_id": null
}
```

### `PATCH /api/ai/interview/sessions/{id}/title`

Body: `{ "title": "..." }` (max 200 chars). Response: `{ "title": "..." }`.

#### Error Responses (all three endpoints)
- `404 Not Found`: session doesn't exist or isn't owned by the caller.
- `429 Too Many Requests`: burst window exceeded (no daily quota - these aren't AI-costed).
