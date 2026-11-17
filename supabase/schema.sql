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
-- role added later; nullable so rows created before it existed stay valid
alter table participants add column if not exists role text check (role in ('Speaker 1','Speaker 2','Researcher'));
create unique index if not exists participants_role_uq on participants (request_id, role);  -- each role once per team

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

-- ---- Selected teams (created when an admin selects a registration) ----
-- Each team logs in to the participant portal with its Request ID. The login lives in Supabase Auth
-- (passwords are bcrypt-hashed by Supabase and never stored by us); teams.user_id points at it.
create table if not exists teams (
  request_id               text primary key references registrations(request_id) on delete cascade,
  user_id                  uuid unique references auth.users(id) on delete set null,
  team_code                text,                              -- optional label typed by the admin
  must_change_password     boolean not null default true,     -- cleared by the portal after the first change
  clarification_edits_used smallint not null default 0 check (clarification_edits_used between 0 and 4),
  round_status             text not null default 'PENDING' check (round_status in ('PENDING','SELECTED','REJECTED')),
  created_at               timestamptz not null default now()
);
create unique index if not exists teams_code_uq on teams (lower(team_code)) where team_code is not null;

create table if not exists clarification_questions (
  id         bigint generated always as identity primary key,
  request_id text not null references teams(request_id) on delete cascade,
  position   smallint not null,
  question   text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (request_id, position)
);

create table if not exists memorial_files (                   -- 4 slots per team: 2 PDF + 2 documents, 2 MB each
  id           bigint generated always as identity primary key,
  request_id   text not null references teams(request_id) on delete cascade,
  slot         smallint not null check (slot between 1 and 4),
  kind         text not null check (kind in ('pdf','doc')),
  file_name    text not null,
  storage_path text not null,
  size_bytes   integer not null check (size_bytes <= 2097152),
  uploaded_at  timestamptz not null default now(),
  unique (request_id, slot)
);

create table if not exists messages (                         -- admin -> team messages
  id         bigint generated always as identity primary key,
  request_id text not null references teams(request_id) on delete cascade,
  sender     text not null,
  body       text not null,
  sent_at    timestamptz not null default now()
);
create index if not exists messages_request_idx on messages (request_id, sent_at desc);

-- Row Level Security: ON everywhere. The backend uses the service-role key (bypasses RLS);
-- the public anon key can reach nothing except reading its own profile.
alter table registrations enable row level security;
alter table participants  enable row level security;
alter table audit_log     enable row level security;
alter table site_content  enable row level security;
alter table profiles      enable row level security;
alter table teams                   enable row level security;
alter table clarification_questions enable row level security;
alter table memorial_files          enable row level security;
alter table messages                enable row level security;
drop policy if exists "read own profile" on profiles;
create policy "read own profile" on profiles for select using (id = auth.uid());
-- no insert/update policy on profiles: nobody can promote themselves. Admins are set by SQL (see README).

-- Public bucket for the rulebook / proposition / memorial / announcement PDFs.
insert into storage.buckets (id, name, public) values ('site-files', 'site-files', true)
on conflict (id) do nothing;

-- Private bucket for memorial submissions (2 MB per file); admins download through short-lived signed links.
insert into storage.buckets (id, name, public, file_size_limit) values ('memorials', 'memorials', false, 2097152)
on conflict (id) do nothing;
