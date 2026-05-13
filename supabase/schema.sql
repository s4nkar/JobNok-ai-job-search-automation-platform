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

-- CV Profile extended fields (run ALTER in Supabase SQL editor to add to existing table)
alter table public.profiles add column if not exists job_title text;
alter table public.profiles add column if not exists phone text;
alter table public.profiles add column if not exists address_street text;
alter table public.profiles add column if not exists address_city text;
alter table public.profiles add column if not exists address_postal_code text;
alter table public.profiles add column if not exists address_country text;
alter table public.profiles add column if not exists date_of_birth date;
alter table public.profiles add column if not exists nationality text;
alter table public.profiles add column if not exists linkedin_url text;
alter table public.profiles add column if not exists github_url text;
alter table public.profiles add column if not exists website_url text;
alter table public.profiles add column if not exists work_authorization text;
alter table public.profiles add column if not exists cv_photo_url text;
alter table public.profiles add column if not exists cv_email text;

-- Supabase Storage bucket for CV photos (run once in SQL editor):
-- insert into storage.buckets (id, name, public) values ('cv-photos', 'cv-photos', true) on conflict do nothing;
-- create policy "Users can upload own cv photo" on storage.objects for insert with check (bucket_id = 'cv-photos' and auth.uid()::text = (storage.foldername(name))[1]);
-- create policy "Users can update own cv photo" on storage.objects for update using (bucket_id = 'cv-photos' and auth.uid()::text = (storage.foldername(name))[1]);
-- create policy "CV photos are publicly readable" on storage.objects for select using (bucket_id = 'cv-photos');

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
-- STARTUP HUNT COMPANIES
-- ============================================================
create table if not exists public.startup_hunt_companies (
  id                  uuid primary key default uuid_generate_v4(),
  user_id             uuid not null references public.profiles(id) on delete cascade,
  company_name        text not null,
  company_domain      text,
  company_website_url text,
  company_careers_url text,
  country             text,
  city                text,
  stage               text,
  company_size        text,
  ai_relevance        text,
  english_friendly    boolean not null default false,
  relocation_support  text,
  source_payload      jsonb not null default '{}',
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

alter table public.startup_hunt_companies enable row level security;

create policy "Users can view own startup hunt companies"
  on public.startup_hunt_companies for select
  using (auth.uid() = user_id);

create policy "Users can insert own startup hunt companies"
  on public.startup_hunt_companies for insert
  with check (auth.uid() = user_id);

create policy "Users can update own startup hunt companies"
  on public.startup_hunt_companies for update
  using (auth.uid() = user_id);

create policy "Users can delete own startup hunt companies"
  on public.startup_hunt_companies for delete
  using (auth.uid() = user_id);

create index if not exists startup_hunt_companies_user_idx
  on public.startup_hunt_companies(user_id);
create index if not exists startup_hunt_companies_name_idx
  on public.startup_hunt_companies(company_name);

create trigger startup_hunt_companies_updated_at
  before update on public.startup_hunt_companies
  for each row execute procedure public.set_updated_at();

-- ============================================================
-- STARTUP HUNT OPPORTUNITIES
-- ============================================================
create table if not exists public.startup_hunt_opportunities (
  id                  uuid primary key default uuid_generate_v4(),
  user_id             uuid not null references public.profiles(id) on delete cascade,
  company_id          uuid references public.startup_hunt_companies(id) on delete set null,
  tracker_application_id uuid references public.job_applications(id) on delete set null,
  company_name        text not null,
  company_domain      text,
  company_website_url text,
  company_careers_url text,
  role_title          text not null,
  location            text not null,
  country             text,
  source_name         text not null,
  source_type         text not null,
  direct_apply_url    text,
  canonical_job_url   text,
  portal_job_url      text,
  posted_at           timestamptz,
  discovered_at       timestamptz not null default now(),
  opportunity_kind    text not null default 'job',
  opportunity_status  text not null default 'saved',
  score_total         numeric not null default 0,
  score_labels        text[] not null default '{}',
  score_reasons       text[] not null default '{}',
  citation_payload    jsonb not null default '{}',
  company_payload     jsonb not null default '{}',
  search_context      jsonb not null default '{}',
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  constraint startup_hunt_opportunity_kind_check
    check (opportunity_kind in ('job', 'outreach_lead')),
  constraint startup_hunt_opportunity_status_check
    check (opportunity_status in ('saved', 'applied', 'contacted', 'skipped'))
);

alter table public.startup_hunt_opportunities enable row level security;

create policy "Users can view own startup hunt opportunities"
  on public.startup_hunt_opportunities for select
  using (auth.uid() = user_id);

create policy "Users can insert own startup hunt opportunities"
  on public.startup_hunt_opportunities for insert
  with check (auth.uid() = user_id);

create policy "Users can update own startup hunt opportunities"
  on public.startup_hunt_opportunities for update
  using (auth.uid() = user_id);

create policy "Users can delete own startup hunt opportunities"
  on public.startup_hunt_opportunities for delete
  using (auth.uid() = user_id);

create index if not exists startup_hunt_opportunities_user_idx
  on public.startup_hunt_opportunities(user_id);
create index if not exists startup_hunt_opportunities_status_idx
  on public.startup_hunt_opportunities(opportunity_status);
create index if not exists startup_hunt_opportunities_company_idx
  on public.startup_hunt_opportunities(company_name);

create trigger startup_hunt_opportunities_updated_at
  before update on public.startup_hunt_opportunities
  for each row execute procedure public.set_updated_at();

-- ============================================================
-- STARTUP HUNT CONTACTS
-- ============================================================
create table if not exists public.startup_hunt_contacts (
  id               uuid primary key default uuid_generate_v4(),
  user_id          uuid not null references public.profiles(id) on delete cascade,
  company_id       uuid references public.startup_hunt_companies(id) on delete set null,
  opportunity_id   uuid references public.startup_hunt_opportunities(id) on delete cascade,
  name             text,
  title            text,
  contact_type     text,
  email            text,
  email_confidence text,
  linkedin_url     text,
  source           text,
  provider_chain   text[] not null default '{}',
  created_at       timestamptz not null default now()
);

alter table public.startup_hunt_contacts enable row level security;

create policy "Users can view own startup hunt contacts"
  on public.startup_hunt_contacts for select
  using (auth.uid() = user_id);

create policy "Users can insert own startup hunt contacts"
  on public.startup_hunt_contacts for insert
  with check (auth.uid() = user_id);

create policy "Users can update own startup hunt contacts"
  on public.startup_hunt_contacts for update
  using (auth.uid() = user_id);

create policy "Users can delete own startup hunt contacts"
  on public.startup_hunt_contacts for delete
  using (auth.uid() = user_id);

create index if not exists startup_hunt_contacts_user_idx
  on public.startup_hunt_contacts(user_id);
create index if not exists startup_hunt_contacts_opportunity_idx
  on public.startup_hunt_contacts(opportunity_id);

-- ============================================================
-- OPPORTUNITY ARTIFACTS
-- Generated docs (resume analysis, cover letters, interview prep) linked to a lead
-- ============================================================
create table if not exists public.opportunity_artifacts (
  id             uuid primary key default uuid_generate_v4(),
  user_id        uuid not null references public.profiles(id) on delete cascade,
  opportunity_id uuid references public.startup_hunt_opportunities(id) on delete cascade,
  artifact_type  text not null,
  tool_used      text not null,
  content        text not null,
  metadata       jsonb not null default '{}',
  created_at     timestamptz not null default now(),
  constraint opportunity_artifact_type_check
    check (artifact_type in ('resume_analysis', 'cover_letter', 'interview_prep'))
);

alter table public.opportunity_artifacts enable row level security;

create policy "Users can view own artifacts"
  on public.opportunity_artifacts for select
  using (auth.uid() = user_id);

create policy "Users can insert own artifacts"
  on public.opportunity_artifacts for insert
  with check (auth.uid() = user_id);

create policy "Users can delete own artifacts"
  on public.opportunity_artifacts for delete
  using (auth.uid() = user_id);

create index if not exists opportunity_artifacts_user_idx
  on public.opportunity_artifacts(user_id);
create index if not exists opportunity_artifacts_opportunity_idx
  on public.opportunity_artifacts(opportunity_id);

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

-- ============================================================
-- ROLE GRANTS
-- Supabase does not automatically grant table-level permissions
-- when tables are created via raw SQL. These grants are required
-- for PostgREST to access tables as service_role or authenticated.
-- Run this section any time new tables are added.
-- ============================================================
do $$
declare
  t text;
  tables text[] := array[
    'profiles',
    'templates',
    'email_campaigns',
    'email_recipients',
    'job_applications',
    'job_search_applications',
    'startup_hunt_companies',
    'startup_hunt_opportunities',
    'startup_hunt_contacts',
    'opportunity_artifacts',
    'linkedin_cache'
  ];
begin
  foreach t in array tables loop
    execute format('grant all on table public.%I to service_role', t);
    execute format('grant all on table public.%I to authenticated', t);
  end loop;
  -- anon gets read-only access only to linkedin_cache (shared, no RLS)
  grant select on table public.linkedin_cache to anon;
end;
$$;
