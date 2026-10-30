# Cover Letter: Low-Level Design (LLD)

**Document Version:** 1.0.0
**Status:** Approved for Production
**Target Audience:** Software Engineers, Module Owners

---

## 1. Code Architecture & Component Directory

```
apps/api/app/modules/cover_letter/
├── __init__.py
├── routes.py              # POST /cover-letter (stream, auto-saves), POST /cover-letter/pdf
├── sessions_routes.py      # Saved-session read-only CRUD: list, get, rename (My Docs) - no /save, see service.py::resolve_session
├── models.py                # CoverLetterSession (cover_letter_sessions table)
├── repository.py            # CoverLetterSessionRepository, incl. get_by_source (job-linked upsert lookup)
├── service.py               # ownership checks, resolve_session (auto-save upsert), display-label fallback, list_sessions_for_docs_page
├── schemas.py              # CoverLetterRequest (now carries opportunity_id/job_search_application_id/session_id), CoverLetterPdfRequest, session schemas
├── text.py                 # Pure helpers: strip_dashes, split_paragraphs — zero WeasyPrint/AI imports
├── rendering.py             # PDF export: Jinja + WeasyPrint (reuses resume_tailor's stack)
└── templates/
    └── cover_letter.html    # Single simple one-page letter layout, no auto-inserted content
```

See `data_flow_and_schema.md` §1.1 for the `cover_letter_sessions` table and §1.2 for `profiles.key_selling_points`/Redis keys this module also touches.

---

## 2. Core Workflows

### 2.1 Generation (`routes.py::generate_cover_letter`)

```python
@router.post("/cover-letter")
async def generate_cover_letter(request: Request, body: CoverLetterRequest, db: AsyncSession = Depends(get_db)):
```

1. **Daily quota** (`rate_limit_cover_letter_per_day`) then **burst window** (`rate_limit_burst_limit`/`rate_limit_burst_window_seconds`, shared setting) — fails open on a Redis error.
2. **Session resolution** (`service.py::resolve_session`), BEFORE any AI call: creates or upserts a `CoverLetterSession` row with placeholder content, committed immediately. Resolution order - a job-linked existing session (one row per job, found via `source_opportunity_id`/`source_application_id`) takes priority over `session_id` (one row per ad-hoc browser visit); a new row is created only when neither applies. This id is returned via the `X-Session-Id` response header, set before `StreamingResponse` starts (the streamed body has no room for a JSON field).
3. **Prompt construction**: system prompt carries the style rules (hook, 2-3 accomplishments, 3-4 paragraphs/250-350 words, no clichés, no dash-class characters, anti-fabrication, prompt-injection framing). User prompt is labeled fields (`COMPANY:`, `ROLE:`, `SELLING POINTS:`, optional `RESUME:`), not free-flowing sentences — the explicit labels make the data/instruction boundary more structurally obvious to the model than natural prose would.
4. **Streamed generation**: `ai_provider.stream_text(prompt, system, max_tokens=900, reasoning_effort=settings.groq_reasoning_effort)`. Each chunk passes through `text.strip_dashes` before being yielded, and is accumulated into `full_text` for the persistence step below.
5. **Mid-stream failure handling**: wrapped in `try/except Exception` — on failure, logs the character count already streamed and appends a bracketed notice (`[Generation interrupted...]`) to the response instead of silently truncating. `StreamingResponse` has already committed to HTTP 200 by the time any exception here could surface (ASGI sends `http.response.start` before the body iterator is first awaited), so this is the best available fix without a wire-protocol redesign — not a workaround for something otherwise fixable.
6. **Final persistence** (`finally` block): whatever was generated (even a partial, interrupted result) is written back into the session row created in step 2 and committed. A totally empty result (failed before any content) deletes that placeholder row instead of leaving an empty "document" behind.

### 2.2 PDF Export (`routes.py::cover_letter_pdf`)

```python
@router.post("/cover-letter/pdf")
async def cover_letter_pdf(request: Request, body: CoverLetterPdfRequest, db: AsyncSession = Depends(get_db)):
```

1. **Daily quota** (`rate_limit_cover_letter_pdf_per_day`, separate from the generation quota — see §3 rationale) then **burst window**.
2. `rendering.render_pdf(body.content)` — renders exactly the text the client sent, no AI call, no auto-inserted salutation or signature. `text.split_paragraphs` splits on blank lines (falling back to single-newline splitting for a hand-edited textarea with no blank-line separation), then `WeasyHTML(string=html).write_pdf()` runs off the event loop via `asyncio.to_thread`.
3. Returns raw PDF bytes with a `Content-Disposition: attachment` header; the frontend controls the actual filename client-side (fetches as a blob, builds its own `<a download>`), since the server-side header's filename isn't easily overridden per-request from the frontend's existing download pattern.

### 2.3 Auto-Save Resolution (`service.py::resolve_session`)

```python
async def resolve_session(db: AsyncSession, user_id: str, body: CoverLetterRequest) -> CoverLetterSession:
```

Called from `routes.py::generate_cover_letter` (see §2.1 step 2), not its own endpoint - there is no `POST /save`. Verifies ownership of `opportunity_id`/`job_search_application_id` (if provided) via `service.verify_opportunity_ownership`/`verify_application_ownership` before trusting either as `source_opportunity_id`/`source_application_id` - same "never trust a client-supplied id" pattern resume_tailor's `/tailor` POST uses. Lives in `service.py` rather than `routes.py` specifically so it stays importable/testable without routes.py's WeasyPrint-importing `rendering.py` in the chain.

### 2.4 List / Get / Rename (`sessions_routes.py`)

- `GET /cover-letter/sessions` - every saved letter for "My Docs", most recent first, via `service.list_sessions_for_docs_page`. Burst-limited.
- `GET /cover-letter/sessions/{id}` - full row, used to reopen a saved letter in the generator page (pre-fills the form + output).
- `PATCH /cover-letter/sessions/{id}/title` - rename, identical shape to resume_tailor's `PATCH /tailor/{id}/title`.

`service._session_display_label` is simpler than resume_tailor's equivalent: `company`/`role` are always literal form fields on a saved session (never AI-guessed), so it's just `session.title or f"{session.role} at {session.company}"` - no opportunity/application fallback lookup, no `is_ai_matched` ambiguity.

---

## 3. Algorithmic / Design Notes

### 3.1 Why AI-generation and PDF-export quotas are separate

Mirrors resume_tailor's exact split (`rate_limit_resume_ai_per_day` vs `rate_limit_resume_pdf_per_day`): AI-costed operations and CPU-costed-but-free rendering operations have different abuse profiles and shouldn't share a budget. `rate_limit_cover_letter_pdf_per_day` defaults to 20 (matched to resume_tailor's PDF quota value — no usage data yet to justify a different number).

### 3.2 `text.py`'s Isolation From `rendering.py`

`strip_dashes` and `split_paragraphs` were originally nested inside `routes.py`/`rendering.py` respectively. Both were pulled into their own dependency-free module specifically so they stay unit-testable without triggering WeasyPrint's native-library import — the same reasoning resume_tailor already applies by keeping its own `rendering.py` as the *only* file in that module that imports WeasyPrint, isolated from `chunker.py`/`matcher.py`/`generation.py`/`validation.py`.

### 3.3 Dash-Class Normalization (`text.py::strip_dashes`)

```python
_DASH_CHARS = str.maketrans({
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
})
```

Covers hyphen, non-breaking hyphen, figure dash, en dash, em dash, horizontal bar, and minus sign — not just em/en dash. The non-breaking hyphen (`U+2011`) specifically was missed by an earlier em/en-dash-only fix and observed live in a real generated letter's compound words (`end‑to‑end`, `AI‑engineered`).

### 3.4 `reasoning_effort` on the Streaming Path (shared `provider.py`)

`_openai_compat_stream` never had `reasoning_effort` support until this module's hardening pass, unlike the non-streaming `_openai_compat_generate`. A gpt-oss-class model with no reasoning cap can spend the entire `max_tokens` budget on hidden chain-of-thought before ever writing visible content — observed live as a cover letter streaming correctly up to a certain point and then silently stopping mid-sentence, with no error (the request technically succeeded; the model just ran out of budget). Fixed at the shared provider layer (only 2 callers at the time: `cover_letter`, `salary` — low blast radius to extend), plus `finish_reason == "length"` detection logged as a warning so a truncation is diagnosable after the fact.

---

## 4. Resilience & Fallback Contracts

| Failure | Behavior |
| :--- | :--- |
| AI provider chain exhausted (generation) | Bracketed notice appended mid-stream (see §2.1.4); nothing silently truncates without explanation. |
| AI provider chain exhausted (before any content yielded) | Same handling — `stream_text` raises `AIGenerationError` once every provider in the chain fails, caught by the same `except Exception`. |
| Length truncation (`finish_reason == "length"`) | Logged as a warning server-side; no user-facing distinction from a normal completion yet (the content itself is just shorter than requested) — `max_tokens=900` plus `reasoning_effort` together are the actual mitigation, not detection alone. |
| WeasyPrint render failure | Not specially handled — propagates as a 500. Rendering a fixed, simple one-page text layout makes this a low-probability path compared to resume_tailor's multi-template system. |
| Redis down (rate limiting) | Fails open on both the daily-quota check and the burst check, consistent with every other limiter in this codebase. |
