# Resume Tailor: API Reference

**Base URL**: `/api/ai`
**Authentication**: Bearer JWT (Clerk) in `Authorization` header, resolved to `user_id` on every request.

---

## 1. Create / Reuse a Tailoring Session

### `POST /api/ai/tailor`

Analyzes a resume against a job description, returning a deterministic match score plus AI-tailored prose. Reuses an existing session for the identical (resume, JD, matcher/prompt version) combination unless `force_refresh=true`.

#### Request (`multipart/form-data`)
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `resume` | file | One of `resume`/`saved_resume_id` | PDF upload, max 5 MB. |
| `saved_resume_id` | string | One of `resume`/`saved_resume_id` | Use an existing "My Resumes" slot instead of a fresh upload. |
| `job_description` | string | Yes | Max 20,000 chars. |
| `force_refresh` | boolean | No | Default `false`. Bypasses session reuse and re-runs the full pipeline. |
| `opportunity_id` | string | No | Links the session to a Startup Hunt opportunity (ownership-verified). |
| `job_search_application_id` | string | No | Links the session to a Recent Job Search tracked application (ownership-verified). |

#### Response (`200 OK`)
```json
{
  "session_id": "e4a2c918-912b-4e12-8409-bf2209d81f10",
  "status": "ready",
  "analysis": {
    "match_score": 72,
    "matched_keywords": ["Python", "FastAPI", "RAG"],
    "missing_keywords": [
      {"keyword": "GenAI", "suggested_placement": "profile_headline"}
    ],
    "score_breakdown": {"core_skills": 75, "responsibilities": 70, "domain": 68, "ats_keywords": 65, "seniority": 75},
    "transferable_strengths": ["Strong cloud native engineering capabilities, with solid foundations in CI/CD..."],
    "critical_missing": ["Hands-on experience with vector databases, embedding models..."],
    "matches": [{"requirement": "...", "best_evidence": "...", "score": 0.81, "match_type": "strong"}],
    "degraded": false
  },
  "tailoring": {
    "target_role": "AI Engineer",
    "target_company": "Deloitte",
    "profile_headline": "AI Engineer | RAG Systems | Transformer Models | MLOps",
    "tailored_summary": "Applied AI Engineer with...",
    "bullet_rewrites": [{"original": "...", "improved": "..."}],
    "summary": "Moderate match — strong RAG/agentic foundation, gaps in...",
    "validation_flags": []
  },
  "ai": {"status": "ok", "provider": "groq"}
}
```

#### Error Responses
- `422 Unprocessable Entity`: neither or both of `resume`/`saved_resume_id` provided.
- `404 Not Found`: `saved_resume_id` doesn't exist or isn't owned by the caller.
- `413 Payload Too Large`: PDF exceeds 5 MB.
- `400 Bad Request`: PDF couldn't be parsed.
- `429 Too Many Requests`: daily `resume_tailor_ai` quota exceeded.

---

## 2. Re-fetch an Existing Session

### `GET /api/ai/tailor/{session_id}`
Returns the same `TailorResponse` shape as §1, from the durable session row — no new AI calls.

---

## 3. Editor

### `GET /api/ai/tailor/{session_id}/editor`
Returns `cv_data` (base resume structure + the tailoring overlay applied) plus the template registry. Lazily triggers `generate_base_cv_data` on first visit if `base_cv_data` hasn't been structured yet for this resume version (cached thereafter, keyed by `STRUCT_PROMPT_VERSION`).

```json
{
  "cv_data": { "...": "full CvDataSchema-shaped object" },
  "session_id": "e4a2c918-...",
  "template_id": "modern-two-column",
  "templates": [{"id": "modern-two-column", "name": "Modern", "...": "..."}],
  "is_draft": false,
  "title": null,
  "draft_version": 0,
  "missing_keywords": ["GenAI", "function calling"]
}
```

### `PATCH /api/ai/tailor/{session_id}/draft`
Debounced autosave of in-progress edits.

#### Request
```json
{ "cv_data": { "...": "edited CvDataSchema-shaped object" }, "base_version": 0 }
```
- `409 Conflict` if `base_version` doesn't match the session's current `draft_version` (another tab saved first).

### `PATCH /api/ai/tailor/{session_id}/title`
```json
{ "title": "Primary Resume" }
```
Max 200 chars.

### `GET /api/ai/tailor/{session_id}/original-pdf`
Returns the original uploaded PDF bytes — only available for sessions created from a `saved_resume_id` (used for "compare with original" in the editor).

---

## 4. Preview & Export

### `POST /api/ai/tailor/{session_id}/preview`
Renders one template as HTML for live preview.
```json
{ "template_id": "modern-two-column", "cv_data": { "...": "..." } }
```

### `POST /api/ai/tailor/{session_id}/preview/thumbnails`
Renders every registered template at once (template-switcher rail).
```json
{ "cv_data": { "...": "..." } }
```
Response: `{"thumbnails": {"modern-two-column": "<html>...", "classic": "<html>..."}}`

### `POST /api/ai/tailor/{session_id}/pdf`
Renders and returns the final PDF (`application/pdf`), no AI involved — pure Jinja + WeasyPrint.
```json
{ "template_id": "modern-two-column", "cv_data": { "...": "..." }, "opportunity_id": null }
```

### `GET /api/ai/tailor/templates`
Template registry metadata (no auth-scoped data — static list).

---

## 5. My Docs (Session List)

### `GET /api/ai/tailor/sessions`
Every generated resume for the caller, for the "My Docs" page.
```json
{
  "sessions": [
    {
      "id": "e4a2c918-...",
      "title": null,
      "display_label": "AI Engineer @ Deloitte",
      "is_ai_matched": true,
      "template_id": "modern-two-column",
      "match_score": 72,
      "created_at": "2026-10-23T14:30:00Z",
      "is_draft": true,
      "preview_html": "<html>...</html>"
    }
  ]
}
```
`display_label` resolves through a fallback chain: user-set title → linked opportunity/application's company+role → AI-parsed `target_role`/`target_company` → `"Standalone Resume"`. `is_ai_matched` is `true` only for the AI-parsed case.

---

## 6. Saved Resumes ("My Resumes")

### `GET /api/ai/resumes`
Lists up to 3 saved resume slots.
```json
{ "resumes": [{"id": "...", "slot": 1, "label": "Primary", "original_filename": "resume.pdf", "created_at": "...", "updated_at": "..."}] }
```

### `PUT /api/ai/resumes/{slot}`
Uploads/replaces the resume in a slot (`slot` is 1–3).

### `PATCH /api/ai/resumes/{slot}`
Renames a slot's label.
```json
{ "label": "Backend-focused" }
```

### `DELETE /api/ai/resumes/{slot}`
Removes a saved resume (`204 No Content`).

### `GET /api/ai/resumes/{slot}/file`
Streams the original PDF — authenticated, server-signs a fresh Cloudinary URL on every call rather than exposing one to the frontend.
