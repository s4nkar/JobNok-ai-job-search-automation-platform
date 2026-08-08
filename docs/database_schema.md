# 🗄️ Database Schema & Security

QuickJob utilizes **Neon (PostgreSQL)** for its primary data store, accessed from FastAPI via **SQLAlchemy async ORM + Alembic migrations** (no query-builder client, no PostgREST, no RLS). Every backend request includes a JWT; the app-level `user_id` filtering enforced by `UserScopedRepository` (`apps/api/app/shared/repository.py`) is what isolates users' data — the sole enforcement layer, not a backstop alongside anything else.

**Schema ownership:** Alembic (`apps/api/alembic/`) is the single source of truth for table/column DDL — schema changes go through `alembic revision --autogenerate` + `alembic upgrade head`. There is no separate SQL file to keep in sync.

## Core Tables

### `profiles`
- **Purpose:** Stores user information. Provisioned by a Clerk webhook (`app/modules/auth/routes.py`, `user.created`) on signup; a lazy lookup-or-create fallback in `core/security.py`'s auth dependency covers the rare case where a request lands before the webhook has processed.
- **Fields:** `id` (app-generated UUID), `clerk_user_id` (maps to Clerk's own user id — the actual FK target every other table's `user_id` implicitly relies on existing), `role`, `email`, `full_name`, `avatar_url`, `plan`, and various CV-related fields (job_title, phone, address, etc.).
- **Access:** Owning user only, enforced by `UserScopedRepository`.

### `templates`
- **Purpose:** Stores reusable message templates created by the user.
- **Fields:** `id`, `user_id`, `name`, `category`, `content`, `placeholders`, `use_count`.
- **Access:** Owning user only, enforced by `UserScopedRepository`.

### `job_applications`
- **Purpose:** Powers the Follow-Up Tracker.
- **Fields:** `id`, `user_id`, `company`, `role`, `status` (Applied, Interview, Offer, Rejected, etc.), `follow_up_date`, `notes`.
- **Access:** Owning user only, enforced by `UserScopedRepository`.

## Email Campaign Tables

### `email_campaigns`
- **Purpose:** Represents a bulk email send operation.
- **Fields:** `id`, `user_id`, `name`, `subject`, `body`, `status` (draft, queued, sending, completed), `delay_seconds`.
- **Access:** Owning user only, enforced by `UserScopedRepository`.

### `email_recipients`
- **Purpose:** Individual recipients tied to a specific campaign. Processed by Celery workers.
- **Fields:** `id`, `campaign_id` (references `email_campaigns`), `email`, `name`, `variables`, `status`, `sent_at`, `error`.
- **Access:** Scoped transitively through the parent `email_campaigns.user_id` (no `user_id` column of its own).

## Opportunity Tracking Tables (Startup Hunt & Job Search)

### `job_search_applications`
- **Purpose:** Automated tracking of jobs discovered or applied to via the job search tool.
- **Fields:** `id`, `user_id`, `job_url`, `company`, `role`, `application_status`.
- **Access:** Owning user only, enforced by `UserScopedRepository`.

### `startup_hunt_companies` & `startup_hunt_opportunities`
- **Purpose:** Used for tracking high-potential startups and specific roles/leads within those companies.
- **Fields:** Company details, domain, AI relevance score, opportunity kind, and status.
- **Access:** Owning user only, enforced by `UserScopedRepository`.

### `opportunity_artifacts`
- **Purpose:** Links generated AI content (resumes, cover letters, prep docs) to specific opportunities.
- **Fields:** `opportunity_id`, `artifact_type`, `content`, `metadata`.
- **Access:** Owning user only, enforced by `UserScopedRepository`.

## Caching

### `linkedin_cache`
- **Purpose:** Stores scraped LinkedIn profile data to reduce API calls and avoid scraping rate limits.
- **Fields:** `id`, `linkedin_url`, `scraped_data`, `scraped_at`.
- **Access:** Shared, unscoped — public LinkedIn profile data is not user-specific.

---

## Data isolation — application layer only

QuickJob has no Row Level Security, no PostgREST, and no Postgres roles for `authenticated`/`anon`/`service_role` — the app connects to Neon with a single ordinary role and does its own scoping in code. Every user-owned table's queries go through `UserScopedRepository` (`apps/api/app/shared/repository.py`), which every module's `service.py` uses and which requires an explicit `user_id` argument on every query — that argument comes from the verified JWT on each request, never from client-supplied input. This is the sole enforcement mechanism; there is no database-level backstop layered underneath it.
