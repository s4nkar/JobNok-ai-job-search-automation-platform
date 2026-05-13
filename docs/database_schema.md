# 🗄️ Database Schema & Security

QuickJob utilizes **Supabase (PostgreSQL)** for its primary data store. Security is enforced at the database level using Row Level Security (RLS) policies. Every backend request includes a JWT, ensuring data isolation between users.

## Core Tables

### `profiles`
- **Purpose:** Stores user information. Auto-created via a Postgres trigger when a user signs up using Supabase Auth.
- **Fields:** `id` (references `auth.users`), `email`, `full_name`, `avatar_url`, `plan`, and various CV-related fields (job_title, phone, address, etc.).
- **RLS:** Users can only view and update their own profile.

### `templates`
- **Purpose:** Stores reusable message templates created by the user.
- **Fields:** `id`, `user_id`, `name`, `category`, `content`, `placeholders`, `use_count`.
- **RLS:** Full CRUD access restricted to the owning `user_id`.

### `job_applications`
- **Purpose:** Powers the Follow-Up Tracker.
- **Fields:** `id`, `user_id`, `company`, `role`, `status` (Applied, Interview, Offer, Rejected, etc.), `follow_up_date`, `notes`.
- **RLS:** Full CRUD access restricted to the owning `user_id`.

## Email Campaign Tables

### `email_campaigns`
- **Purpose:** Represents a bulk email send operation.
- **Fields:** `id`, `user_id`, `name`, `subject`, `body`, `status` (draft, queued, sending, completed), `delay_seconds`.
- **RLS:** Full CRUD access restricted to the owning `user_id`.

### `email_recipients`
- **Purpose:** Individual recipients tied to a specific campaign. Processed by Celery workers.
- **Fields:** `id`, `campaign_id` (references `email_campaigns`), `email`, `name`, `variables`, `status`, `sent_at`, `error`.
- **RLS:** Users can interact with recipients if they own the parent `email_campaigns` record.

## Opportunity Tracking Tables (Startup Hunt & Job Search)

### `job_search_applications`
- **Purpose:** Automated tracking of jobs discovered or applied to via the job search tool.
- **Fields:** `id`, `user_id`, `job_url`, `company`, `role`, `application_status`.
- **RLS:** Restricted to the owning `user_id`.

### `startup_hunt_companies` & `startup_hunt_opportunities`
- **Purpose:** Used for tracking high-potential startups and specific roles/leads within those companies.
- **Fields:** Company details, domain, AI relevance score, opportunity kind, and status.
- **RLS:** Restricted to the owning `user_id`.

### `opportunity_artifacts`
- **Purpose:** Links generated AI content (resumes, cover letters, prep docs) to specific opportunities.
- **Fields:** `opportunity_id`, `artifact_type`, `content`, `metadata`.
- **RLS:** Restricted to the owning `user_id`.

## Caching

### `linkedin_cache`
- **Purpose:** Stores scraped LinkedIn profile data to reduce API calls and avoid scraping rate limits.
- **Fields:** `id`, `linkedin_url`, `scraped_data`, `scraped_at`.
- **Security:** **No RLS**. This is a shared cache because public LinkedIn profile data is not user-specific. The backend accesses this table using the Supabase Service Role key.

---

## Row Level Security (RLS) Implementation Details

A typical RLS policy in QuickJob ensures that the `user_id` column matches the authenticated user's ID (`auth.uid()`):

```sql
create policy "Users can view own templates"
  on public.templates for select
  using (auth.uid() = user_id);
```

This guarantees that even if an API endpoint were to have a logic flaw, the database itself prevents cross-tenant data leakage.
