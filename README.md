# SASTRA International Commercial Arbitration Moot Court Competition — Registration Starter

React + FastAPI starter with an Apple-inspired UI, Excel workbook storage, admin review, audit events, XLSX export, and Gmail SMTP notifications.

## Requirements
- Python 3.10+
- Node.js 20+

## 1. Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env. Gmail SMTP requires a Google App Password (2-Step Verification enabled).
uvicorn app.main:app --reload
```
API docs: http://127.0.0.1:8000/docs

The first run creates `data/registrations.xlsx` and `data/admins.xlsx` from the configured files. Add admin email(s) to the `admins` sheet (or edit `data/admins.xlsx`) and restart. The default seed admin email is `raghav.kartik2005@gmail.com`; change `ADMIN_PASSWORD` in `.env` before use. Admin access requires both an active email in the Admins sheet and the configured password.

## 2. Frontend
In another terminal:
```bash
cd frontend
npm install
npm run dev
```
Open the URL printed by Vite. Admin sign-in is available from the top-right button.

## Email testing
The `.env.example` routes all notifications to `thanosragu2005@gmail.com` and CCs `raghav.kartik2005@gmail.com` by default. This is deliberately test-safe. Set `SMTP_USER` and `SMTP_APP_PASSWORD` to your own Gmail address and Google App Password. Never use your normal Google password. The app records mail delivery errors in logs/audit rather than losing the registration.

## Event dates
Edit `backend/app/config.json` (`event_start`, `event_end`, `registration_open`, `registration_close`). Timestamps are interpreted in the configured `timezone`.

## Excel storage layout
- `registrations.xlsx`: one row per team, including up to three participants.
- `admins.xlsx`: admin email, active flag, display name.
- `audit.xlsx`: append-only audit events searchable by request ID.

Excel is suitable for a small demo / pilot. It is not a safe multi-worker or high-concurrency production database: use PostgreSQL (which you mentioned you have) before public launch, and add HTTPS, rate limiting, stronger admin identity, backups, and deployment secrets.


## Gmail SMTP troubleshooting
The starter intentionally does not include Gmail credentials. If `SMTP_USER` or `SMTP_APP_PASSWORD` is blank, the API records `email_skipped` in `audit.xlsx` and prints a warning in the terminal; no email will be sent.

1. Use a Gmail account you control as `SMTP_USER`.
2. Enable Google 2-Step Verification for that account.
3. Create a Google App Password in your Google Account security settings (if the account is eligible).
4. Put the Gmail address in `SMTP_USER` and the 16-character App Password in `SMTP_APP_PASSWORD` in `backend/.env`. Do not use your normal Gmail password.
5. Keep `EMAIL_TEST_MODE=true` while testing. Every message is routed to `TEST_RECIPIENT` with `TEST_CC` copied.
6. Stop and restart Uvicorn after editing `.env`.
7. Submit a new test registration and watch the backend Terminal for `Email not sent`, `SMTP failure`, or a successful request. Check Gmail Spam, All Mail, and search for the subject too.
8. If it still fails, inspect the matching request ID in `backend/data/audit.xlsx` for `email_skipped`, `email_failed`, or `email_sent`. The last two indicate whether the SMTP server accepted the message; SMTP acceptance is not a guarantee of inbox placement.

Never commit `.env` or share the App Password. Gmail SMTP uses `smtp.gmail.com`, port `587`, with STARTTLS.

## Site content (documents, announcements, dates)
Everything that changes after launch lives in `backend/config/`:
- `site.json`: document slots (rules, proposition, memorial), announcements (each can carry a PDF), important dates, prize money, FAQs and coordinator contacts.
- `files/`: the published PDFs (`rules.pdf`, `proposition.pdf`, `memorial.pdf`).

Admins manage all of it from the admin portal, under "Publish documents & updates": upload/replace/remove a PDF, add or remove announcements, edit the dates. Changes appear on the public site immediately. The public site reads `GET /api/site` and serves PDFs from `GET /api/files/{key}`.
Note: on Vercel the filesystem is ephemeral, so uploads there need object storage before real use.
