# Smart Templates — Production Hardening Playbook

**Status:** Production-ready (2026-10-30)

Smart Templates had **zero** hardening before this pass — no length limits, no rate limiting of any kind, no server-side category enforcement, and a client-trusted counter with a real race condition. None of this tool's gaps are AI/scrape-related (there's no AI or scraping in this tool at all); every finding below is about treating a "simple" CRUD tool with the same input-validation and rate-limiting discipline as every other tool, per CLAUDE.md's blanket rules ("Input length limits," "Rate limit: Redis per user/tool") which don't carve out an exception for non-AI tools.

---

## 1. Zero rate limiting, zero length bounds

**Found**: `TemplateIn`/`TemplateUpdate` had only ad-hoc minimum-length checks (`name` ≥ 2 chars, `content` ≥ 10 chars) via custom `@field_validator`s — no maximum at all, at either the Pydantic layer or the DB column (`name`/`content` were plain `Text`, no `CheckConstraint`). A single `POST /api/templates` could carry an arbitrarily large `content` string. Separately, none of the four endpoints (`GET`, `POST`, `PUT`, `DELETE`) had any rate limiting — not a daily quota, not a burst window — the only tool in this codebase in that state.

**Fix**:
- `name` capped at 100 chars, `content` at 5,000 — both as `Field(..., max_length=...)` (replacing the custom validators with the standard declarative style used everywhere else in this codebase) and as DB `CheckConstraint`s (migration `f4b8d1c9e3a7`).
- A burst-window check on **all five** endpoints (list/create/update/delete/use), plus a daily quota on create specifically (`rate_limit_templates_create_per_day`, default 50) as a storage-abuse ceiling — not AI-cost related, since there's no AI call here, just a ceiling on unbounded row creation.

**Verified**: before writing the migration, queried the live DB directly for any existing row that would violate the new constraints (`WHERE char_length(name) > 100 OR char_length(content) > 5000 OR category NOT IN (...)`) — zero rows, table was empty, safe to add directly rather than needing a backfill/cleanup step first. `uv run ruff check`, full `pytest` suite (676 passing after this pass's 20 new tests), migration applied to the live DB and `alembic current` confirmed at the new head.

## 2. `category` accepted any string - the frontend's Zod enum was the only enforcement

**Found**: `TemplateIn.category: str` — no constraint at all server-side. The frontend's `z.enum(TEMPLATE_CATEGORIES)` only protects requests that actually go through that form; any direct API call (or a future second frontend, a script, a bug) could persist a garbage category with nothing to stop it.

**Fix**: `TemplateCategory = Literal["Cold DM - Recruiter", "Cold DM - Hiring Manager", "Follow-Up", "Referral Ask", "Email Outreach", "Custom"]`, matching the frontend's enum value-for-value, plus a matching DB `CheckConstraint` as the second layer.

**Verified**: live-tested both an unknown category and an oversized `name` against the real `TemplateIn` schema — both correctly raised `ValidationError` before ever reaching the DB.

## 3. A real bug found while auditing the frontend: the category color map didn't match any real category

**Found**: auditing the frontend's `CategoryBadge` component (`apps/web/app/(dashboard)/templates/page.tsx`) turned up a second, unrelated bug while checking whether `category` needed server-side validation. The color-lookup map was keyed on `'LinkedIn'`, `'Email'`, `'Follow-up'`, `'Thank You'`, `'Custom'` — but `TEMPLATE_CATEGORIES` (`apps/web/lib/types.ts`) actually contains `'Cold DM - Recruiter'`, `'Cold DM - Hiring Manager'`, `'Follow-Up'`, `'Referral Ask'`, `'Email Outreach'`, `'Custom'`. None of the real category values (except literally `'Custom'`) ever matched a key in that map — `'Follow-Up'` vs. the map's lowercase `'Follow-up'` is a one-character casing mismatch that's easy to miss by eye. Every category badge except `'Custom'` was silently falling back to the generic gray "Custom" style, with no error anywhere to notice it.

**Fix**: rewrote the color map to use the real category strings, keeping the original design intent (the two "cold DM" categories share a recognizable blue outreach color, everything else stays neutral slate).

**Verified**: `tsc --noEmit`, `eslint` - both clean. This is a pure styling fix with no logic to unit test; worth a visual spot-check (create one template per category, confirm each badge now shows its intended color) before fully trusting it.

## 4. `use_count` was a client-computed value on a generic `PUT` - a real lost-update race

**Found**: `copyToClipboard` (frontend) computed `(selected.use_count || 0) + 1` in JavaScript and sent it via `PUT /api/templates/{id}`. Two rapid copies of the same template, or two browser tabs open on it, could both read the same `use_count` and both PUT the same incremented value - a genuine lost update, not just a display staleness issue, since nothing else ever recomputes this value.

**Fix**: removed `use_count` from `TemplateUpdate` entirely and added `POST /{id}/use`, which increments atomically at the DB layer via `UPDATE templates SET use_count = use_count + 1 ... RETURNING *` (`service.py::TemplateRepository.increment_use_count`). The frontend now calls that endpoint instead of computing anything itself.

**Verified**: live-tested against the real DB. First attempt (reusing one long-lived Python session across three sequential increment calls) produced `1, 1` on the second call - looked like a bug at first, but tracing it showed this was SQLAlchemy's identity-map/`synchronize_session` behavior interacting with a reused session, not a flaw in the atomic UPDATE itself. Re-tested with a **fresh session per call** - matching exactly how `get_db()` hands every real HTTP request its own session - and got the correct `1, 2, 3`. Documented in `architecture_lld.md` §2.3 so a future reader writing a similar test script doesn't get fooled the same way.

---

## What's explicitly *not* done (accepted tradeoffs)

- No cap on total templates per user (unlike `SavedResume`'s fixed 3-slot limit elsewhere in this codebase). Accepted: template rows are tiny (a few KB of text each), there's no external cost per row the way a scrape or an AI call has, and no evidence of abuse to size a cap against yet.
- No automated visual regression test for the category-color fix (§3) - confirmed by code/type inspection, not a rendered screenshot comparison. Worth a manual spot-check.
- Prebuilt templates (`PREBUILT_TEMPLATES`) were not audited as part of this pass — they're static, checked-in data with no user input path, out of scope for an input-validation/rate-limiting hardening pass.

## Environment limitations encountered while verifying this pass

None specific to this module — unlike Cover Letter/Resume Tailor, `templates/routes.py` has no WeasyPrint (or any other native-library) dependency, so every file imports and runs natively on this Windows dev host with no workaround needed. All verification (schema validation, the atomic increment, the pre-migration existing-data check) was run directly against the real configured database.
