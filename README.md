# SASTRA International Commercial Arbitration Moot Competition — Registration Starter

React + FastAPI app with Supabase (Postgres, Auth, Storage): team registration, admin review, audit events, XLSX export, and Gmail SMTP notifications.

## Requirements
- Python 3.10+
- Node.js 20+

## 0. Supabase setup (one time)
1. Create a free project at supabase.com (note the database password; you won't need it for this app).
2. **SQL Editor -> New query**: paste all of `supabase/schema.sql` -> Run. This creates the tables, the signup trigger, Row Level Security and the `site-files` storage bucket. Safe to re-run.
3. **Project Settings -> API**: copy the Project URL, the `anon` key and the `service_role` key.
   - `service_role` is a secret: backend `.env` / Vercel env only, never in frontend code.
4. **Authentication -> Providers -> Email**: turn **off** "Allow new users to sign up" (admins are invited, not self-registered). Later, when the participant portal exists, turn it back on.
5. **Authentication -> Users -> Add user -> Create new user**: enter the admin email + a strong password, tick "Auto Confirm User".
6. Make that user an admin (SQL Editor):
   ```sql
   update profiles set role = 'admin', display_name = 'Your Name' where email = 'admin@example.com';
   ```
   Every new Auth user starts as `participant`; only this SQL (or the dashboard table editor) can promote.
7. Optional: copy the old Excel data and `config/site.json` into Supabase (see "Importing old data" below).

## 1. Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SMTP settings.
uvicorn app.main:app --reload
```
API docs: http://127.0.0.1:8000/docs

## 2. Frontend
In another terminal:
```bash
cd frontend
cp .env.example .env   # set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY
npm install
npm run dev
```
Open the URL printed by Vite, then `/#admin` and sign in with the admin account from step 5.

## Importing old data
```bash
cd backend && source .venv/bin/activate
python scripts/import_legacy.py              # site.json + registrations + audit + rules.pdf
python scripts/import_legacy.py --site-only  # skip registrations/audit (e.g. they were test data)
```
Safe to re-run. Afterwards `backend/data/*.xlsx` is no longer used and can be deleted.

## Deploying on Vercel
Add these in Project Settings -> Environment Variables: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `FRONTEND_ORIGIN` (your site URL), `EMAIL_TEST_MODE`, `SMTP_*`. Vercel also has a Supabase integration (Marketplace) that fills in the Supabase ones for you.
Vercel limits request bodies to 4.5 MB, so published PDFs are capped at 4 MB.

## Admin portal (`/#admin`)
Sign in with a Supabase Auth account whose `profiles.role` is `admin`. Three tabs:
- **Registrations** (primary): download buttons at the top (all clarification questions, all participants, registrations), the review queue, and Select / Reject. **Selecting** a team (optionally with a team code and a note) creates its Participant Portal login in Supabase Auth (User ID = the Request ID, generated 10-character password: 4 letters + 6 digits, hashed by Supabase) and emails the login details to the coach and all participants, organisers on CC.
- **Team management**: every selected team. Open one for a left menu: Team details (incl. team code, Reset password), Clarification questions, Memorial submission, Status (pending / selected / rejected) and Send message (emailed to the team, and kept in the `messages` table).
- **Site content** (secondary): documents, announcements, dates, FAQs, contacts, prizes.

Teams have no real email on their Auth account (their identifier is `<request-id>@teams.icac.invalid`, hidden from users), so a forgotten password is handled by the admin using **Reset password**. `EMAIL_CC` (default: the two organiser addresses) is copied on every email.

## Participant portal (`/#portal`)
Selected teams sign in with their **Request ID** and the emailed temporary password (the public site has a "Login" link). First sign-in forces a password change. Left menu: Team details (with the team code), Clarification questions, Memorial submission, Messages.
- **Clarification questions** open when the *Moot proposition* PDF is published under Site content. A team's first save is free; after that it may edit its saved questions 4 times. Answers are released on the public site.
- **Memorial submission** opens when the *Memorial guidelines* PDF is published. 4 files per team (2 PDF + 2 Word `.doc`/`.docx`), 2 MB each, stored in the private `memorials` bucket; admins download them from the team page.

## Data model (Supabase Postgres)
- `registrations` + `participants`: one team per university (unique index), 1-3 participants each.
- `audit_log`: append-only events (also records site-content changes under `request_id = 'SITE'`).
- `site_content`: documents, announcements, schedule, FAQs, contacts, prizes (one JSON row per section).
- `teams` (+ `clarification_questions`, `memorial_files`, `messages`): created when a registration is selected; one Auth login per team.
- `profiles`: one row per Supabase Auth user; `role` is `admin` or `participant`.
- Storage buckets: `site-files` (public PDFs) and `memorials` (private, 2 MB per file, for the participant portal).
All tables have Row Level Security on; only the backend (service-role key) reads or writes them.

## Email testing
The `.env.example` routes all notifications to `thanosragu2005@gmail.com` and CCs `raghav.kartik2005@gmail.com` by default. This is deliberately test-safe. Set `SMTP_USER` and `SMTP_APP_PASSWORD` to your own Gmail address and Google App Password. Never use your normal Google password. The app records mail delivery errors in logs/audit rather than losing the registration.

## Event dates
Edit `backend/app/config.json` (`event_start`, `event_end`, `registration_open`, `registration_close`). Timestamps are interpreted in the configured `timezone`.

## Gmail SMTP troubleshooting
The starter intentionally does not include Gmail credentials. If `SMTP_USER` or `SMTP_APP_PASSWORD` is blank, the API records `email_skipped` in `audit_log` and prints a warning in the terminal; no email will be sent.

1. Use a Gmail account you control as `SMTP_USER`.
2. Enable Google 2-Step Verification for that account.
3. Create a Google App Password in your Google Account security settings (if the account is eligible).
4. Put the Gmail address in `SMTP_USER` and the 16-character App Password in `SMTP_APP_PASSWORD` in `backend/.env`. Do not use your normal Gmail password.
5. Keep `EMAIL_TEST_MODE=true` while testing. Every message is routed to `TEST_RECIPIENT` with `TEST_CC` copied.
6. Stop and restart Uvicorn after editing `.env`.
7. Submit a new test registration and watch the backend Terminal for `Email not sent`, `SMTP failure`, or a successful request. Check Gmail Spam, All Mail, and search for the subject too.
8. If it still fails, query `audit_log` in Supabase for the request ID and look for `email_skipped`, `email_failed`, or `email_sent`. The last two indicate whether the SMTP server accepted the message; SMTP acceptance is not a guarantee of inbox placement.

Never commit `.env` or share the App Password. Gmail SMTP uses `smtp.gmail.com`, port `587`, with STARTTLS.

## Site content (documents, announcements, dates)
Everything that changes after launch lives in Supabase: the `site_content` table and the `site-files` bucket. Admins manage it from the admin portal under "Publish documents & updates" (upload/replace/remove PDFs, announcements, dates, FAQs, contacts, prizes). Changes appear on the public site immediately. `GET /api/site` serves the content; `/api/files/{key}` redirects to the stored PDF.
