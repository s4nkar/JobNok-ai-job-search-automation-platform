# Database Architecture & Schema Master Reference

**Document Version:** 2.0.0  
**Status:** Production Baseline  

---

## 1. Overview & Data Isolation Architecture

The backend utilizes **Supabase-hosted PostgreSQL** managed via **SQLAlchemy 2.0 Async ORM** (`asyncpg` driver) and **Alembic migrations** (`apps/api/alembic/`).

### Key Principles
1. **Schema Authority**: Alembic is the single source of truth for DDL changes. Schema modifications are generated via `alembic revision --autogenerate` and executed via `alembic upgrade head`.
2. **Application-Layer Tenant Isolation**: All user-owned tables enforce tenant isolation at the service layer via `UserScopedRepository` (`apps/api/app/shared/repository.py`), requiring an explicit `user_id` query filter derived directly from verified JWT claims.
3. **Database Triggers**: Timestamp fields (`updated_at`) on key tables are updated server-side via PostgreSQL `BEFORE UPDATE` trigger function `public.set_updated_at()`.

---

## 2. Platform Table Schemas

### 2.1 Identity & User Profile (`profiles`)
- **Table**: `profiles`
- **Purpose**: Stores user account profiles, Clerk user mappings, CV metadata, and contact details. Provisioned via Clerk webhook (`/api/auth/webhooks/clerk`).
- **Schema DDL**:
  ```sql
  CREATE TABLE profiles (
      id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      clerk_user_id TEXT UNIQUE,
      role TEXT DEFAULT 'user',
      email TEXT NOT NULL,
      full_name TEXT,
      avatar_url TEXT,
      plan TEXT NOT NULL DEFAULT 'free',
      job_title TEXT,
      phone TEXT,
      address_street TEXT,
      address_city TEXT,
      address_postal_code TEXT,
      address_country TEXT,
      date_of_birth DATE,
      nationality TEXT,
      linkedin_url TEXT,
      github_url TEXT,
      website_url TEXT,
      work_authorization TEXT,
      cv_photo_url TEXT,
      cv_email TEXT,
      created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
  );
  ```

---

### 2.2 Shared Job Cache (`jobs`)
- **Table**: `jobs`
- **Purpose**: Shared, deduplicated global cache of external job listings (from Adzuna, Bundesagentur, Arbeitnow, and background crawlers).
- **Indexes**:
  - `jobs_canonical_url_idx`: B-tree index on `canonical_url`.
  - `jobs_country_posted_at_idx`: Compound B-tree index on `(country, posted_at DESC)`.
  - `jobs_title_trgm_idx`: GIN trigram index on `title gin_trgm_ops`.
  - `jobs_description_trgm_idx`: GIN trigram index on `description gin_trgm_ops`.

---

### 2.3 Global Startup Registry (`company_registry`)
- **Table**: `company_registry`
- **Purpose**: Deduplicated global catalog of discovered startups tracked by background crawlers.
- **Indexes**: Partial unique index on `domain WHERE domain IS NOT NULL`, GIN trigram indexes on `city` and `country`.

---

### 2.4 Follow-Up Tracker (`job_applications`)
- **Table**: `job_applications`
- **Purpose**: Powers the active job application tracker dashboard.
- **Columns**: `id`, `user_id` (FK `profiles.id`), `company`, `role`, `applied_at`, `status` (`'Applied'`, `'Interview'`, `'Offer'`, `'Rejected'`), `follow_up_date`, `notes`, `salary_min`, `salary_max`, `updated_at`, `created_at`.

---

### 2.5 Recent Job Search Applications (`job_search_applications`)
- **Table**: `job_search_applications`
- **Purpose**: Tracks saved/applied job search listings per user. Linked to `job_applications` via `tracker_application_id`.

---

### 2.6 Startup Hunt Subsystem Tables
- **`startup_hunt_companies`**: Per-user saved startup companies snapshot.
- **`startup_hunt_opportunities`**: Per-user saved job vacancies/outreach leads. Linked to `jobs.id` via `job_id` FK.
- **`startup_hunt_contacts`**: Discovered contacts (Founders, CEOs, Recruiters) linked to opportunities.
- **`startup_hunt_sources`**: Global curated and user-custom ATS board search configurations (`resolved`, `pending`, `failed`).
- **`opportunity_artifacts`**: AI-generated cover letters, resume analysis, and interview prep docs linked to opportunities.

---

### 2.7 Startup Scout Subsystem Tables
- **`startup_scout_companies`**: Discovered/saved startup scout profiles (`pending`, `crawling`, `enriched`, `failed`).
- **`startup_scout_contacts`**: Discovered executive contacts with confidence score and Apollo verification flags.

---

### 2.8 Bulk Email Campaigns (`email_campaigns` & `email_recipients`)
- **`email_campaigns`**: Campaign definitions (`draft`, `queued`, `sending`, `completed`).
- **`email_recipients`**: Individual campaign recipients processed by ARQ background workers. Unique constraint on `(campaign_id, email)`.

---

### 2.9 Templates, Caching & Analytics
- **`templates`**: User-saved message templates (`id`, `user_id`, `name`, `category`, `content`, `placeholders`, `use_count`).
- **`linkedin_cache`**: Shared scraped profile JSON cache (`linkedin_url`, `scraped_data`, `scraped_at`).
- **`tool_usage_events`**: Feature usage analytics events (`user_id`, `tool_slug`, `created_at`).

---

## 3. Tool Schema Deep Dives

For complete schema DDLs, index definitions, and entity relationship diagrams, see:

- [Recent Job Search Schema Reference](file:///d:/Projects/Vibe%20Code/quickjob-ai-job-search-automation-platform/docs/recent_job_search/data_flow_and_schema.md)
- [Startup Hunt Schema Reference](file:///d:/Projects/Vibe%20Code/quickjob-ai-job-search-automation-platform/docs/startup_hunt/data_flow_and_schema.md)
- [Startup Scout Schema Reference](file:///d:/Projects/Vibe%20Code/quickjob-ai-job-search-automation-platform/docs/startup_scout/data_flow_and_schema.md)
