-- QuickJob Phase 1 — Supabase Schema
-- Run this in the Supabase SQL editor to create all tables, indexes, and RLS policies.

-- ============================================================
-- EXTENSIONS
-- ============================================================
create extension if not exists "uuid-ossp";

-- ============================================================
-- PROFILES
-- Auto-created when a user signs up via Supabase Auth trigger
-- ============================================================
create table if not exists public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  email       text not null,
  full_name   text,
  avatar_url  text,
  plan        text not null default 'free',
  created_at  timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "Users can view own profile"
  on public.profiles for select
  using (auth.uid() = id);

create policy "Users can update own profile"
  on public.profiles for update
  using (auth.uid() = id);

-- Auto-create profile on signup
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email, full_name, avatar_url)
  values (
    new.id,
    new.email,
    new.raw_user_meta_data->>'full_name',
    new.raw_user_meta_data->>'avatar_url'
  );
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ============================================================
-- TEMPLATES
-- ============================================================
create table if not exists public.templates (
  id           uuid primary key default uuid_generate_v4(),
  user_id      uuid not null references public.profiles(id) on delete cascade,
  name         text not null,
  category     text not null default 'Custom',
  content      text not null,
  placeholders text[] not null default '{}',
  use_count    int not null default 0,
  created_at   timestamptz not null default now()
);

alter table public.templates enable row level security;

create policy "Users can view own templates"
  on public.templates for select
  using (auth.uid() = user_id);

create policy "Users can insert own templates"
  on public.templates for insert
  with check (auth.uid() = user_id);

create policy "Users can update own templates"
  on public.templates for update
  using (auth.uid() = user_id);

create policy "Users can delete own templates"
  on public.templates for delete
  using (auth.uid() = user_id);

create index if not exists templates_user_id_idx on public.templates(user_id);
create index if not exists templates_category_idx on public.templates(category);

-- ============================================================
-- EMAIL CAMPAIGNS
-- ============================================================
create table if not exists public.email_campaigns (
  id             uuid primary key default uuid_generate_v4(),
  user_id        uuid not null references public.profiles(id) on delete cascade,
  name           text not null,
  subject        text not null,
  body           text not null,
  status         text not null default 'draft',  -- draft | queued | sending | completed | paused | failed
  delay_seconds  int not null default 30,
  created_at     timestamptz not null default now()
);

alter table public.email_campaigns enable row level security;

create policy "Users can view own campaigns"
  on public.email_campaigns for select
  using (auth.uid() = user_id);

create policy "Users can insert own campaigns"
  on public.email_campaigns for insert
  with check (auth.uid() = user_id);

create policy "Users can update own campaigns"
  on public.email_campaigns for update
  using (auth.uid() = user_id);

create policy "Users can delete own campaigns"
  on public.email_campaigns for delete
  using (auth.uid() = user_id);

create index if not exists campaigns_user_id_idx on public.email_campaigns(user_id);
create index if not exists campaigns_status_idx on public.email_campaigns(status);

-- ============================================================
-- EMAIL RECIPIENTS
-- ============================================================
create table if not exists public.email_recipients (
  id           uuid primary key default uuid_generate_v4(),
  campaign_id  uuid not null references public.email_campaigns(id) on delete cascade,
  email        text not null,
  name         text not null default '',
  variables    jsonb not null default '{}',
  status       text not null default 'queued',  -- queued | sending | sent | failed
  sent_at      timestamptz,
  error        text
);

alter table public.email_recipients enable row level security;

create policy "Users can view own recipients"
  on public.email_recipients for select
  using (
    exists (
      select 1 from public.email_campaigns c
      where c.id = campaign_id and c.user_id = auth.uid()
    )
  );

create policy "Users can insert own recipients"
  on public.email_recipients for insert
  with check (
    exists (
      select 1 from public.email_campaigns c
      where c.id = campaign_id and c.user_id = auth.uid()
    )
  );

create policy "Users can update own recipients"
  on public.email_recipients for update
  using (
    exists (
      select 1 from public.email_campaigns c
      where c.id = campaign_id and c.user_id = auth.uid()
    )
  );

create index if not exists recipients_campaign_id_idx on public.email_recipients(campaign_id);
create index if not exists recipients_status_idx on public.email_recipients(status);

-- ============================================================
-- JOB APPLICATIONS (Follow-Up Tracker)
-- ============================================================
create table if not exists public.job_applications (
  id             uuid primary key default uuid_generate_v4(),
  user_id        uuid not null references public.profiles(id) on delete cascade,
  company        text not null,
  role           text not null,
  applied_at     date not null default current_date,
  status         text not null default 'Applied',
  -- Applied | Phone Screen | Interview | Offer | Rejected | Withdrawn
  follow_up_date date,
  notes          text,
  salary_min     int,
  salary_max     int,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

alter table public.job_applications enable row level security;

create policy "Users can view own applications"
  on public.job_applications for select
  using (auth.uid() = user_id);

create policy "Users can insert own applications"
  on public.job_applications for insert
  with check (auth.uid() = user_id);

create policy "Users can update own applications"
  on public.job_applications for update
  using (auth.uid() = user_id);

create policy "Users can delete own applications"
  on public.job_applications for delete
  using (auth.uid() = user_id);

create index if not exists applications_user_id_idx on public.job_applications(user_id);
create index if not exists applications_status_idx on public.job_applications(status);
create index if not exists applications_follow_up_idx on public.job_applications(follow_up_date);

-- Auto-update updated_at
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger job_applications_updated_at
  before update on public.job_applications
  for each row execute procedure public.set_updated_at();

-- ============================================================
-- JOB SEARCH APPLICATIONS
-- ============================================================
create table if not exists public.job_search_applications (
  id                     uuid primary key default uuid_generate_v4(),
  user_id                uuid not null references public.profiles(id) on delete cascade,
  job_url                text not null,
  job_url_canonical      text not null,
  source_name            text not null,
  external_job_id        text,
  company                text not null,
  role                   text not null,
  location               text not null,
  posted_at              timestamptz,
  discovered_at          timestamptz not null default now(),
  applied_at             timestamptz,
  application_status     text not null default 'saved',
  tracker_application_id uuid references public.job_applications(id) on delete set null,
  citation_payload       jsonb not null default '{}',
  search_context         jsonb not null default '{}',
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  constraint job_search_applications_status_check
    check (application_status in ('saved', 'applied', 'skipped'))
);

alter table public.job_search_applications enable row level security;

create policy "Users can view own job search applications"
  on public.job_search_applications for select
  using (auth.uid() = user_id);

create policy "Users can insert own job search applications"
  on public.job_search_applications for insert
  with check (auth.uid() = user_id);

create policy "Users can update own job search applications"
  on public.job_search_applications for update
  using (auth.uid() = user_id);

create policy "Users can delete own job search applications"
  on public.job_search_applications for delete
  using (auth.uid() = user_id);

create unique index if not exists job_search_applications_user_job_url_key
  on public.job_search_applications(user_id, job_url_canonical);
create index if not exists job_search_applications_status_idx
  on public.job_search_applications(application_status);
create index if not exists job_search_applications_tracker_idx
  on public.job_search_applications(tracker_application_id);
create index if not exists job_search_applications_posted_idx
  on public.job_search_applications(posted_at desc);

create trigger job_search_applications_updated_at
  before update on public.job_search_applications
  for each row execute procedure public.set_updated_at();

-- ============================================================
-- LINKEDIN CACHE
-- Shared cache — no RLS (profile data is public on LinkedIn)
-- ============================================================
create table if not exists public.linkedin_cache (
  id            uuid primary key default uuid_generate_v4(),
  linkedin_url  text unique not null,
  scraped_data  jsonb not null default '{}',
  scraped_at    timestamptz not null default now()
);

-- No RLS on linkedin_cache — shared across users for the same URL
-- Service role key is used for reads/writes from the backend

create index if not exists linkedin_cache_url_idx on public.linkedin_cache(linkedin_url);
create index if not exists linkedin_cache_scraped_at_idx on public.linkedin_cache(scraped_at);
