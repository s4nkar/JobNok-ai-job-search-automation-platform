# Interview Prep — Production Hardening Playbook

**Status:** Production-ready (2026-10-29)

Interview Prep went from a completely unhardened, fire-and-forget endpoint (no length limits, no burst limit, no response validation, fragile `text.find("{")` JSON parsing, no persistence) to the same production bar as Resume Tailor and Cover Letter in one pass this session. This documents the full hardening, organized the same way as `docs/resume_tailor/production_hardening_playbook.md` — what was done, why, where, and how it was verified.

---

## Quick checklist — see `docs/cover_letter/production_hardening_playbook.md`

Interview Prep was audited together with Cover Letter in the same pass, since both tools share the exact same generate-then-auto-save shape. That playbook's checklist and its §1/§2 (single-flight locking, the resume_tailor job-link race it also uncovered) apply here unchanged — not duplicated in full below, just the module-specific details that differ.

---

## 1. Starting point: zero hardening

**Found** (`routes.py`, before this session): `InterviewPrepRequest`/`InterviewRegenerateRequest` had no length limits at all on `job_description`/`question` (a direct DoS vector per this codebase's input-length convention); no burst-window check (daily quota only, and even that was a flat 10/day with no separate regenerate bucket); the LLM response was parsed with a bare `text.find("{")`/`text.rfind("}")` plus `json.loads`, no `response_format=json_object`, no schema validation of the result's shape — a malformed or wrong-shape response would either crash with an unhandled exception or ship broken data straight to the frontend.

**Fix**: the full set of changes already covered in `architecture_hld.md`/`architecture_lld.md` — length bounds, `response_format=json_object` + `validate_interview_response`'s field-by-field lenient validation, a separate regenerate quota, and (this pass) single-flight locking. Not re-listed item-by-item here since those documents already describe the current state in full; this playbook's job is the *why* and the *verification*, not a duplicate spec.

## 2. Single-flight lock — see Cover Letter's playbook §1/§2 for the full writeup

**Found**: identical gap to Cover Letter's — a daily quota and burst window, but nothing stopping two concurrent requests from the same user both passing the burst check and both proceeding. For `/interview` specifically, auto-save made this worse: two concurrent requests could both resolve "no existing session for this job" via `get_by_source` and both create one.

**Fix**: `interview_gen:{user_id}:lock` on `/interview` (reject-fast, 429, released in a `finally`), and a *finer-grained* `interview_regen:{user_id}:{session_id}:{question_index}:lock` on `/interview/regenerate` — deliberately scoped per-question rather than per-user, since a user plausibly wants to regenerate several different questions' answers in quick succession while reviewing a kit, and a per-user lock there would make that normal workflow feel broken.

**Verified**: `uv run ruff check`, full `pytest` suite (656 passing), live test of the underlying `acquire_lock`/`delete_cached` primitives against real Redis (see Cover Letter's playbook §1 for the transcript — same primitive, same test). Not verified against a real two-request race (no way to drive two genuinely concurrent HTTP calls in this environment) — verified by code trace instead.

## 3. A real correctness bug found during live end-to-end testing: one mismatched enum value silently deleted 10 questions

**Found**: live-testing generation against the real AI provider (not a mock) with the exact job description a user had pasted, the response came back with `"questions": []` — all ten questions gone. Tracing it: `InterviewQuestionSchema.framework` was typed as `Literal["STAR", "Behavioral", "Technical", "Situational"]`, but the system prompt's own question-mix instruction explicitly asks for "2 motivational" questions. The model correctly followed its instructions and tagged two questions `"Motivational"` — a value the schema's `Literal` didn't allow. `validate_interview_response`'s field-by-field validator (by design) falls back to that *field's* default on a mismatch — but `questions` is validated as a single `list[InterviewQuestionSchema]` field, so one bad item among ten invalidated the whole list down to `[]`, not just that one question.

**Fix**: relaxed `framework` from a `Literal` to plain `str` (`schemas.py`). This is a cosmetic display tag only — the frontend renders it as a badge and branches on nothing about its value — unlike `seniority`/`dsa_likely`/`system_design_likely`, which gate real conditional rendering/behavior and correctly stay strict `Literal`/`bool` types. Also added `"Motivational"` to the prompt's own documented enum list in `prompts.py` so the model's instructions and the (now-informal) expected set stay self-consistent for a future reader, even though nothing enforces it anymore.

**This is the single most important finding in this pass**: it was caught *only* because generation was tested against the real provider with real content, not a mock. A schema this strict, validated only against hand-written test fixtures that happen not to include a `"Motivational"` tag, would have shipped this bug — every real generation would have silently returned zero questions, with the response still a `200 OK` and a validly-shaped (if empty) payload, no error anywhere to notice.

**Verified**: re-ran the same live generation after the fix — `questions` came back with all 10 items, `frameworks: ['STAR', 'STAR', 'Behavioral', 'Technical', 'Technical', 'Situational', 'Situational', 'Motivational', 'Motivational', 'Role-specific challenge']`. Also tested a non-engineering JD (Marketing Manager) to confirm `dsa_questions`/`system_design_questions` correctly come back empty rather than forced, and tested a fictional company name to confirm `company_context` comes back `null` rather than fabricated. All three live checks are reproduced in this session's history with the actual provider output shown.

## 4. Caching and circuit breaker — same conclusion as Cover Letter, not re-investigated separately

No deterministic, cacheable step exists here either (see Cover Letter's playbook §3 — the reasoning is identical: free-text LLM generation, including the explicitly-intentional case where a regenerate should produce different wording for identical input). The shared `_CIRCUIT_SCOPE = "ai_llm"` breaker in `app/ai/llm/provider.py` already covers this module's `generate_text` calls with zero module-specific wiring.

---

## What's explicitly *not* done (accepted tradeoffs)

- Same per-user-not-per-job lock granularity tradeoff on `/interview` as Cover Letter's `/cover-letter` (see that playbook's own "not done" section) — accepted for the same reason (infrequent, one-shot generations).
- `_extract_json`'s defensive trim (see `architecture_lld.md` §3.3) is still there even though `response_format=json_object` should make it unnecessary — kept as cheap insurance, not removed, since there's no cost to keeping it and removing it has nothing to gain.
- No automated regression test pins the exact "Motivational" bug class (a schema field's allowed values silently diverging from what the prompt actually asks for) — the fix addresses the specific instance found, not a general lint/CI check that would catch the *next* time a prompt and a schema drift apart. Worth considering if this pattern recurs.

## Environment limitations encountered while verifying this pass

Unlike Cover Letter and Resume Tailor, this module has no WeasyPrint dependency at all (`rendering.py` doesn't exist here) — `import app.modules.interview_prep.routes`/`.service`/`.schemas` all work natively on this Windows dev host with no import-chain workaround needed. The live end-to-end generation tests in §3 above were run directly against the real configured AI provider (not mocked), which is how the "Motivational" bug was actually caught.
