# Smart Templates: Low-Level Design (LLD)

**Document Version:** 1.0.0
**Status:** Approved for Production

---

## 1. Code Architecture

```
apps/api/app/modules/templates/
├── __init__.py
├── routes.py      # GET, POST, PUT /{id}, DELETE /{id}, POST /{id}/use — all rate-limited
├── schemas.py      # TemplateIn, TemplateUpdate — length bounds + category Literal
├── models.py        # Template (templates table) — CheckConstraints mirror the schema bounds
└── service.py        # extract_placeholders (pure), TemplateRepository (incl. atomic increment_use_count), CRUD orchestration
```

No `rendering.py`, no AI provider import, no scrape client — this module has none of the infrastructure every other tool needs.

---

## 2. Core Workflows

### 2.1 Create (`routes.py::create_template`)

1. **Daily quota** (`rate_limit_templates_create_per_day`, default 50) then **burst window**.
2. `service.extract_placeholders(body.content)` — regex `\{\{([^}]+)\}\}`, deduped, first-occurrence order preserved.
3. `TemplateRepository(db).create(user_id, **body.model_dump(), placeholders=placeholders)`.

### 2.2 Update (`routes.py::update_template`)

`body.model_dump(exclude_unset=True)` — distinguishes "field not sent" from "field sent as null," so a partial `PUT` only touches what the client actually included. If `content` is among the sent fields, placeholders are re-extracted from the new content before the update; `name`/`category` changes don't touch `placeholders` at all.

### 2.3 Atomic Use-Count Increment (`service.py::TemplateRepository.increment_use_count`)

```python
stmt = (
    self._scoped(update(self.model), user_id)
    .where(self.model.id == id_)
    .values(use_count=self.model.use_count + 1)
    .returning(self.model)
)
```

A single `UPDATE ... RETURNING`, not a read-then-write — `use_count + 1` is evaluated by Postgres against the row's current value at the moment of the write, not a value computed in Python moments earlier. Confirmed live against the real DB: three sequential calls (each in its own fresh session, matching how `get_db()` gives every real HTTP request its own session) returned `1, 2, 3`. A single shared, long-lived session reused across calls can produce a stale read due to SQLAlchemy's identity-map/`synchronize_session` behavior — not a concern in production, where `get_db()` always hands out a fresh session per request, but worth knowing if writing a test script that reuses one session across multiple calls.

### 2.4 Delete / List

Both delegate straight to `UserScopedRepository`'s generic `delete`/`list`, scoped by `user_id` — no module-specific logic beyond the burst-limit check.

---

## 3. Design Notes

### 3.1 Why `use_count` Isn't on `TemplateUpdate`

**Found**: the frontend's `copyToClipboard` previously computed `(selected.use_count || 0) + 1` in JavaScript and sent it via `PUT /{id}`. Two rapid copies (or two tabs open on the same template) could both read the same stale count and both write the same incremented value — a lost update, not just a display inaccuracy, since nothing else recomputes this value afterward.

**Fix**: removed `use_count` from `TemplateUpdate` entirely (a client can no longer set it to an arbitrary value via `PUT`) and added a dedicated `POST /{id}/use` that increments atomically at the DB layer (§2.3). The frontend now calls that endpoint instead of computing the new value itself.

### 3.2 Why Category Became a `Literal`

**Found**: `TemplateIn.category: str` accepted any string — the frontend's Zod `z.enum(TEMPLATE_CATEGORIES)` only protects a browser client; a direct API call bypasses it entirely, and nothing on the backend stopped a garbage category from being persisted.

**Fix**: `TemplateCategory = Literal["Cold DM - Recruiter", "Cold DM - Hiring Manager", "Follow-Up", "Referral Ask", "Email Outreach", "Custom"]`, matching `apps/web/lib/types.ts::TEMPLATE_CATEGORIES` field-for-field, plus a DB `CheckConstraint` as a second layer in case a future code path ever writes this table without going through the schema.

---

## 4. Resilience & Fallback Contracts

| Failure | Behavior |
| :--- | :--- |
| Redis down (rate limiting) | Fails open on both the daily-quota check and the burst check, consistent with every other limiter in this codebase. |
| A field exceeds its length cap, or `category` isn't a known value | `422`, rejected before touching the DB. |
| `PUT`/`DELETE`/`POST /use` on a template that doesn't exist or isn't owned by the caller | `404` — `UserScopedRepository`'s `user_id` scoping means a mismatched id and a nonexistent id are indistinguishable from the outside, by design. |
