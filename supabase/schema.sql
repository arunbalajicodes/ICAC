-- SASTRA Moot registration schema. Paste this whole file into Supabase -> SQL Editor -> Run.
-- Safe to re-run: everything is "if not exists" / "or replace".

create table if not exists registrations (
  request_id    text primary key,                       -- 'SASTRA-XXXXXXXXXX'
  created_at    timestamptz not null default now(),
  status        text not null default 'REVIEW_PENDING'
                check (status in ('REVIEW_PENDING','APPROVED','REJECTED')),
  university    text not null,
  country       text not null,
  coach_name    text not null,
  coach_email   text not null,
  coach_phone   text not null,
  decision_at   timestamptz,
  decision_by   text,
  decision_note text
);
-- one team per university (case/space-insensitive); race-safe
create unique index if not exists registrations_university_uq on registrations (lower(btrim(university)));
create index if not exists registrations_status_idx on registrations (status, created_at desc);

create table if not exists participants (                -- 1 to 3 per team
  id          bigint generated always as identity primary key,
  request_id  text not null references registrations(request_id) on delete cascade,
  position    smallint not null check (position between 1 and 3),
  name        text not null,
  email       text not null,
  year        text not null,
  unique (request_id, position)
);

create table if not exists audit_log (                   -- append-only; request_id also holds 'SITE'
  id          bigint generated always as identity primary key,
  at          timestamptz not null default now(),
  request_id  text not null,
  actor       text,
  action      text not null,
  from_status text,
  to_status   text,
  details     text
);
create index if not exists audit_request_idx on audit_log (request_id, at);

create table if not exists site_content (                -- documents, announcements, schedule, faqs, contacts, prizes
  key        text primary key,
  value      jsonb not null,
  updated_at timestamptz not null default now()
);

-- One profile per Supabase Auth user. role decides admin vs (future) participant portal.
create table if not exists profiles (
  id           uuid primary key references auth.users(id) on delete cascade,
  email        text not null,
  display_name text,
  role         text not null default 'participant' check (role in ('admin','participant')),
  active       boolean not null default true
);

create or replace function handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, email) values (new.id, lower(new.email));
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function handle_new_user();

-- Row Level Security: ON everywhere. The backend uses the service-role key (bypasses RLS);
-- the public anon key can reach nothing except reading its own profile.
alter table registrations enable row level security;
alter table participants  enable row level security;
alter table audit_log     enable row level security;
alter table site_content  enable row level security;
alter table profiles      enable row level security;
drop policy if exists "read own profile" on profiles;
create policy "read own profile" on profiles for select using (id = auth.uid());
-- no insert/update policy on profiles: nobody can promote themselves. Admins are set by SQL (see README).

-- Public bucket for the rulebook / proposition / memorial / announcement PDFs.
insert into storage.buckets (id, name, public) values ('site-files', 'site-files', true)
on conflict (id) do nothing;
