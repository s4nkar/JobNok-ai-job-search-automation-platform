-- Local-dev-only stub of Supabase's internal auth schema.
-- Production Postgres (Supabase-hosted) already has the real auth schema
-- managed by GoTrue; this stub exists purely so supabase/schema.sql's
-- `profiles.id references auth.users(id)` FK and `auth.uid() = ...` RLS
-- policies can be applied when running the app against a local Postgres for
-- development. RLS policies aren't the enforcement layer for this app
-- (app-level user_id filtering is — see app/shared/repository.py) and
-- aren't tracked by Alembic either way, so a null-returning stub is enough.
create schema if not exists auth;

-- raw_user_meta_data is required by schema.sql's handle_new_user() trigger,
-- which reads new.raw_user_meta_data->>'full_name' / 'avatar_url' on insert.
create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(),
  email text,
  raw_user_meta_data jsonb not null default '{}'::jsonb
);

create or replace function auth.uid() returns uuid
  language sql stable
  as $$ select null::uuid $$;

-- Stub the Supabase PostgREST roles so schema.sql's closing `grant ... to
-- service_role/authenticated/anon` block succeeds too.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon;
  end if;
end
$$;
