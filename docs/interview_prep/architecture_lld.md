# Interview Prep: Low-Level Design (LLD)

**Document Version:** 1.0.0
**Status:** Approved for Production
**Target Audience:** Software Engineers, Module Owners

---

## 1. Code Architecture & Component Directory

```
apps/api/app/modules/interview_prep/
├── __init__.py
├── routes.py              # POST /interview, POST /interview/regenerate - rate limit, lock, prompt, validate, persist
├── sessions_routes.py      # Saved-session read-only CRUD: list, get, rename (My Docs) - no /save, see service.py::resolve_session
├── models.py                # InterviewPrepSession (interview_prep_sessions table)
├── repository.py            # InterviewPrepSessionRepository, incl. get_by_source (job-linked upsert lookup)
├── service.py               # ownership checks, resolve_session, apply_regenerated_answer, display-label fallback, list_sessions_for_docs_page
├── schemas.py              # InterviewPrepRequest, InterviewRegenerateRequest, response-validation schemas, session schemas
├── prompts.py               # INTERVIEW_SYSTEM_PROMPT, build_interview_prompt, build_regenerate_prompt
└── text.py                  # Pure helpers: strip_dashes, strip_dashes_deep — zero AI/DB imports
```

No `rendering.py` / `templates/` — this module has no PDF export or any other rendering concern, unlike Resume Tailor/Cover Letter.

---

## 2. Core Workflows

### 2.1 Generation (`routes.py::generate_interview_questions`)

```python
@router.post("/interview")
async def generate_interview_questions(request: Request, body: InterviewPrepRequest, db: AsyncSession = Depends(get_db)):
```

1. **Daily quota** (`rate_limit_interview_per_day`) then **burst window** (`rate_limit_burst_limit`/`rate_limit_burst_window_seconds`).
2. **Single-flight lock** (`interview_gen:{user_id}:lock`, `_GENERATION_LOCK_TTL_SECONDS = 60`) — rejects a second concurrent request from the same user with `429` before any AI call or DB write, rather than letting both proceed and either double-spend AI cost or create duplicate sessions. Released in a `finally` the moment this request's own work ends (success or any failure), not left to the full TTL.
3. **Prompt construction**: `build_interview_prompt` prepends trusted `COMPANY:`/`ROLE:` lines (from an already-known Startup Hunt lead or tracked application) ahead of the JD text when given, so the model doesn't have to guess a company name out of free text.
4. **Generation**: `ai_provider.generate_text(prompt, INTERVIEW_SYSTEM_PROMPT, max_tokens=4000, tier="heavy", response_format={"type": "json_object"}, reasoning_effort=settings.groq_reasoning_effort)`.
5. **JSON extraction + validation**: `_extract_json` (defensive `find("{")`/`rfind("}")` trim, belt-and-suspenders even though `response_format=json_object` should already guarantee a clean object) then `validate_interview_response` (field-by-field, lenient — see `architecture_hld.md` §4.4) then `strip_dashes_deep` (recursive dash-class normalization).
6. **Auto-save**: `interview_prep_service.resolve_session(db, user_id, body, sanitized)` — upserts into the right row (see §2.3 below).
7. **Response**: the validated/sanitized result plus `"session_id": str(session.id)`.

### 2.2 Regeneration (`routes.py::regenerate_interview_answer`)

```python
@router.post("/interview/regenerate")
async def regenerate_interview_answer(request: Request, body: InterviewRegenerateRequest, db: AsyncSession = Depends(get_db)):
```

1. **Daily quota** (`rate_limit_interview_regenerate_per_day` — separate bucket from generation, see `config.py`'s comment) then **burst window**.
2. **Single-flight lock**, scoped by `(user_id, session_id, question_index)` rather than just `user_id` — two *different* questions' regenerate calls from the same user are independent work and shouldn't block each other; only a double-click on the *same* question's button should.
3. **Generation**: `ai_provider.generate_text(prompt, max_tokens=500, tier="light", response_format={"type": "json_object"}, reasoning_effort=...)` — a much smaller call than full generation (one answer, not ten questions plus technical prep), using the lighter non-reasoning model tier. `body.job_description` is truncated to `_REGENERATE_JD_CONTEXT_CHARS = 1500` chars for this call specifically — enough context to stay on-topic, regardless of how long the original (up to 12,000-char) JD was.
4. **Persist-back**: if `session_id`/`question_index` were given, `interview_prep_service.apply_regenerated_answer` patches `result.questions[question_index]` in place (merging the new `answer_framework`/`tips` into the existing question, keeping its `question` text and `framework` tag untouched) and writes the updated `result` back. Silently no-ops if the session or index doesn't exist (e.g. a stale `session_id`) rather than failing the regenerate the user is actually waiting on.

### 2.3 Auto-Save Resolution (`service.py::resolve_session`)

```python
async def resolve_session(db: AsyncSession, user_id: str, body: InterviewPrepRequest, result: dict[str, Any]) -> InterviewPrepSession:
```

Called after the result is already generated and validated — unlike Cover Letter, this endpoint isn't streaming, so there's no need to create a placeholder row before the AI call just to get an id early. Resolution order: a job-linked existing session (`get_by_source`, found via `source_opportunity_id`/`source_application_id`) takes priority over `session_id` (one row per ad-hoc browser visit); a new row is created only when neither applies. `verify_opportunity_ownership`/`verify_application_ownership` re-check ownership before either id is trusted.

### 2.4 List / Get / Rename (`sessions_routes.py`)

- `GET /interview/sessions` — every saved kit for "My Docs", most recent first, via `service.list_sessions_for_docs_page`.
- `GET /interview/sessions/{id}` — full row, used to reopen a saved kit in the generator page (pre-fills the JD, role assessment, questions, DSA/system-design prep).
- `PATCH /interview/sessions/{id}/title` — rename, identical shape to Resume Tailor's/Cover Letter's own title-rename endpoints.

`service._session_display_label`: title → `"{role} at {company}"` (when both are literal, known fields) → `"{role_family} Interview Kit"` (falling back to the AI-inferred `role_assessment.role_family` from the saved result — a plain pasted JD often has neither company nor role known) → `"Interview Prep Kit"` (generic fallback). No `is_ai_matched` ambiguity flag like Resume Tailor's equivalent needs — `role_family` is only ever used as a last-resort label here, never presented as if it were a confirmed job match.

---

## 3. Algorithmic / Design Notes

### 3.1 Why Generation and Regeneration Have Separate Daily Quotas

Same "split by cost profile" reasoning as Resume Tailor's AI/PDF split and Cover Letter's generation/PDF split, but for a different reason here: both calls are AI-costed (unlike a PDF render), but a user might reasonably regenerate several individual answers per one generated kit — sharing the main generation quota would let a few regenerates on one kit eat into the budget meant for "how many kits can you generate today."

### 3.2 Single-Flight Lock Granularity: Per-User (Generate) vs. Per-Question (Regenerate)

The generate lock is coarse (`interview_gen:{user_id}:lock`) because generation itself is a single, relatively infrequent action per JD. The regenerate lock is finer (`interview_regen:{user_id}:{session_id}:{question_index}:lock`) specifically because a user plausibly wants to regenerate *several different* questions' answers in quick succession while reviewing a kit — locking per-user there would make the UI feel broken (clicking "Regenerate" on question 3 while question 1's regenerate is still in flight would be rejected for no good reason). See `docs/interview_prep/production_hardening_playbook.md` §1 for the full concurrency-safety writeup.

### 3.3 `_extract_json`'s Defensive Trim

`response_format=json_object` (Groq/OpenAI-compatible JSON mode) should make `raw` pure JSON with nothing else around it. `_extract_json` still does a defensive `find("{")`/`rfind("}")` trim before `json.loads` rather than calling `json.loads(raw)` directly — cheap insurance against a provider's JSON mode occasionally including incidental whitespace or, in the fallback-chain case, a provider whose JSON mode is less strictly conformant than Groq's. Mirrors the same defensive style already used in Resume Tailor's own LLM-JSON-handling code.

---

## 4. Resilience & Fallback Contracts

| Failure | Behavior |
| :--- | :--- |
| AI provider chain exhausted (generation) | `503`, nothing persisted (no partial row created — unlike Cover Letter's streaming case, there's no placeholder row to clean up since persistence only happens after a successful, validated result). |
| AI provider chain exhausted (regenerate) | `503`, the saved kit's existing answer for that question is left untouched (never partially overwritten). |
| LLM returns malformed JSON | `500`, logged with the exception repr only (never raw content). |
| A response field has the wrong shape/type (e.g. `seniority` not one of the four allowed values) | That one field falls back to its own default; sibling fields are unaffected — see `architecture_hld.md` §4.4. |
| Two concurrent identical requests (double-click, retry, two tabs) | The second is rejected with `429` before doing any work — see §2.1/§2.2 and the production hardening playbook. |
| Redis down (rate limiting, locking) | Rate limits fail open (allow); the single-flight lock also fails open (`acquired = True` on an exception) — consistent with every other limiter/lock in this codebase, an unreachable Redis degrades to "allow," not "block everyone." |
