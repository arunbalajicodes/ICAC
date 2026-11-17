from __future__ import annotations
import json, os, re, secrets, smtplib, string, time, uuid, logging
from datetime import datetime
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Literal, Optional
from fastapi import Depends, FastAPI, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import unquote
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, ValidationError
from openpyxl import Workbook
from postgrest.exceptions import APIError
from supabase import create_client
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE.parent / ".env")
with open(BASE / "config.json", encoding="utf-8") as f:
    CONFIG = json.load(f)
TZ = ZoneInfo(CONFIG.get("timezone", "Asia/Kolkata"))

# Service-role key bypasses Row Level Security: keep it server-side only, never in the frontend.
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
BUCKET = "site-files"

app = FastAPI(title="SASTRA Moot Registration API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class Participant(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    year: str = Field(min_length=1, max_length=40)
    role: Literal["Speaker 1", "Speaker 2", "Researcher"]

class RegistrationIn(BaseModel):
    university: str = Field(min_length=2, max_length=180)
    country: str = Field(min_length=2, max_length=80)
    coach_name: str = Field(min_length=2, max_length=120)
    coach_email: EmailStr
    coach_phone: str = Field(min_length=6, max_length=30)
    participants: list[Participant] = Field(min_length=1, max_length=3)

class DecisionIn(BaseModel):
    decision: str
    note: str = Field(default="", max_length=1000)
    team_code: str = Field(default="", max_length=40)   # optional label, only used when selecting

class TeamPatch(BaseModel):
    team_code: Optional[str] = Field(default=None, max_length=40)    # "" clears it
    round_status: Optional[Literal["PENDING", "SELECTED", "REJECTED"]] = None

class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=3000)

class PasswordIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=72)  # 72 = bcrypt's limit

class QuestionsIn(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=20)


def now(): return datetime.now(TZ).isoformat(timespec="seconds")
def parse_time(key): return datetime.fromisoformat(CONFIG[key]).replace(tzinfo=TZ)

def flatten(reg: dict) -> dict:
    """DB row (+ nested participants) -> the flat participant1_* shape the admin UI and Excel export use."""
    ps = {p["position"]: p for p in reg.pop("participants", [])}
    for i in (1, 2, 3):
        p = ps.get(i, {})
        reg[f"participant{i}_name"], reg[f"participant{i}_email"], reg[f"participant{i}_year"], reg[f"participant{i}_role"] = p.get("name"), p.get("email"), p.get("year"), p.get("role")
    return reg

def log_audit(request_id, actor, action, from_status="", to_status="", details=""):
    sb.table("audit_log").insert({"request_id": request_id, "actor": actor, "action": action, "from_status": from_status or None, "to_status": to_status or None, "details": details or None}).execute()

# ---- Email wording: edit the text here ----
SHORT_EVENT = "SASTRA ICAC Moot Court Competition 2027"
SIGNOFF = "Thanks and Regards,\nICAC Co-ordinators,\nSchool of Law,\nSASTRA Deemed To Be University"
DEFAULT_CC = "127118023@sastra.ac.in,128087006@sastra.ac.in"  # organisers copied on every mail; override with EMAIL_CC
QUOTE_ID = "Please quote the Request ID below in any correspondence regarding this registration."

def received_email(coach, university):
    return (f"Registration Received — {SHORT_EVENT}",
        f"Dear {coach},\n\n"
        f"Thank you for registering {university} for the {CONFIG['event_name']}, hosted by the School of Law, SASTRA Deemed To Be University.\n\n"
        "We confirm that your team's registration has been received. It is now under review by the organising committee, and we will write to you again as soon as a decision has been made.\n\n"
        + QUOTE_ID)

def rejection_email(coach, university, note=""):
    extra = f"\n\nNote from the organising committee: {note}" if note else ""
    return (f"Registration Decision — {SHORT_EVENT}",
        f"Dear {coach},\n\n"
        f"Thank you for your interest in the {CONFIG['event_name']}. After careful review, we regret to inform you that the registration of {university} could not be approved on this occasion."
        + extra + "\n\n"
        "Should you wish to seek clarification, please contact the organising committee using the contact details on the competition website.\n\n"
        "We appreciate your interest and wish you every success in your future endeavours.\n\n" + QUOTE_ID)

def selection_email(coach, university, request_id, password, team_code, note=""):
    extra = f"\n\nNote from the organising committee: {note}" if note else ""
    code_line = f"\n  Team code: {team_code}" if team_code else ""
    return (f"Team Selected — {SHORT_EVENT}",
        f"Dear {coach},\n\n"
        f"We are pleased to inform you that {university} has been selected to participate in the {CONFIG['event_name']}. Congratulations, and welcome to the competition."
        + extra + "\n\n"
        "Your team's login details for the Participant Portal are given below:\n\n"
        f"  User ID: {request_id}\n  Temporary password: {password}{code_line}\n\n"
        "To sign in, please visit the competition website and click \"Login\" to reach the Participant Portal. "
        "For your security, kindly change this temporary password immediately after your first login, and do not share it outside your team.\n\n"
        "All official communication, including clarifications and updates, will be sent to this email address.\n\n"
        "We look forward to your team's participation.\n\n" + QUOTE_ID)

def password_reset_email(coach, request_id, password):
    return (f"Participant Portal — New Temporary Password — {SHORT_EVENT}",
        f"Dear {coach},\n\n"
        "As requested, a new temporary password has been issued for your team's Participant Portal account. Any previous password no longer works.\n\n"
        f"  User ID: {request_id}\n  Temporary password: {password}\n\n"
        "Please sign in through the \"Login\" link on the competition website and change this password immediately. Kindly do not share it outside your team.\n\n" + QUOTE_ID)

def message_email(coach, text):
    return (f"Message from the Organising Committee — {SHORT_EVENT}", f"Dear {coach},\n\n{text}")

def addresses(*lists):
    """Flatten, trim and de-duplicate (case-insensitive) email addresses, keeping order."""
    seen, out = set(), []
    for item in (a.strip() for l in lists for a in ([l] if isinstance(l, str) else l)):
        if item and item.lower() not in seen: seen.add(item.lower()); out.append(item)
    return out

def send_status_email(request_id, subject, body, recipients):
    """recipients = coach + participants. CC (EMAIL_CC) goes to the organisers on every mail."""
    # Test mode always routes to configured test recipients, never to real registrants.
    test_mode = os.getenv("EMAIL_TEST_MODE", "true").lower() == "true"
    to_list = addresses(os.getenv("TEST_RECIPIENT", "thanosragu2005@gmail.com")) if test_mode else addresses(recipients)
    cc_list = addresses(os.getenv("TEST_CC", "raghav.kartik2005@gmail.com").split(",") if test_mode else os.getenv("EMAIL_CC", DEFAULT_CC).split(","))
    cc_list = [a for a in cc_list if a.lower() not in {t.lower() for t in to_list}]  # nobody gets the same mail twice
    to_addr, cc_addr = ", ".join(to_list), ", ".join(cc_list)
    smtp_user, smtp_pass = os.getenv("SMTP_USER", ""), os.getenv("SMTP_APP_PASSWORD", "")
    if not smtp_user or not smtp_pass:
        logging.warning("Email not sent (SMTP not configured). request_id=%s subject=%s", request_id, subject)
        log_audit(request_id, "system", "email_skipped", details="SMTP credentials not configured")
        return "skipped"
    msg = EmailMessage(); msg["Subject"] = subject; msg["From"] = smtp_user; msg["To"] = to_addr
    if cc_addr: msg["Cc"] = cc_addr
    msg.set_content(f"{body}\n\nRequest ID: {request_id}\n\n{SIGNOFF}\n")
    try:
        with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587")), timeout=15) as server:
            server.starttls(); server.login(smtp_user, smtp_pass); server.send_message(msg)
        log_audit(request_id, "system", "email_sent", details=f"to={to_addr}; cc={cc_addr}; subject={subject}")
        return "sent"
    except Exception as exc:
        logging.exception("SMTP failure for %s", request_id)
        log_audit(request_id, "system", "email_failed", details=str(exc)[:500])
        return "failed"

# Verifying a login costs 1-2 round trips to Supabase, so remember the result briefly (per warm server instance).
# ponytail: an admin who is deactivated keeps access for up to AUTH_TTL seconds; lower it (or drop the cache) if that matters.
AUTH_TTL, _auth_cache = 60, {}

def cached(key, load):
    hit = _auth_cache.get(key)
    if hit and hit[0] > time.monotonic(): return hit[1]
    value = load()   # errors (401/403) propagate and are never cached
    if len(_auth_cache) > 500:
        for k in [k for k, v in _auth_cache.items() if v[0] <= time.monotonic()]: del _auth_cache[k]
    _auth_cache[key] = (time.monotonic() + AUTH_TTL, value)
    return value

def bearer(authorization):
    if not authorization or not authorization.lower().startswith("bearer "): raise HTTPException(401, "Sign-in required")
    return authorization.split(" ", 1)[1]

def verified_user_id(token):
    """Supabase Auth proves who you are (a signed, expiring JWT)."""
    try: user = sb.auth.get_user(token).user
    except Exception: raise HTTPException(401, "Session expired; sign in again")
    if not user: raise HTTPException(401, "Session expired; sign in again")
    return user.id

def load_admin(token):
    rows = sb.table("profiles").select("email,display_name,role,active").eq("id", verified_user_id(token)).limit(1).execute().data
    if not rows or rows[0]["role"] != "admin" or not rows[0]["active"]:
        raise HTTPException(403, "This account is not an active admin")
    return {"email": rows[0]["email"], "display_name": rows[0]["display_name"] or rows[0]["email"]}

def require_admin(authorization: Optional[str] = Header(default=None)):
    """The profiles table decides if you're an active admin."""
    token = bearer(authorization)
    return cached(("admin", token), lambda: load_admin(token))

@app.get("/api/health")
def health(): return {"ok": True, "event": CONFIG["event_name"]}

@app.get("/api/config")
def public_config():
    current = datetime.now(TZ)
    opens, closes = parse_time("registration_open"), parse_time("registration_close")
    return {"event_name":CONFIG["event_name"], "event_start":CONFIG["event_start"], "event_end":CONFIG["event_end"], "registration_open":CONFIG["registration_open"], "registration_close":CONFIG["registration_close"], "registration_open_now":opens <= current <= closes, "timezone":CONFIG.get("timezone"), "max_participants_per_team":CONFIG.get("max_participants_per_team",3), "team_email_domain":TEAM_EMAIL_DOMAIN, "email_test_mode":os.getenv("EMAIL_TEST_MODE","true").lower()=="true"}

@app.get("/api/admin/me")
def admin_me(admin=Depends(require_admin)): return admin

@app.post("/api/registrations", status_code=201)
def create_registration(payload: RegistrationIn):
    current = datetime.now(TZ)
    if not (parse_time("registration_open") <= current <= parse_time("registration_close")):
        raise HTTPException(403, "Registration is currently closed.")
    if len(payload.participants) > int(CONFIG.get("max_participants_per_team", 3)):
        raise HTTPException(422, "A team may have at most three participants.")
    if len({p.role for p in payload.participants}) != len(payload.participants):
        raise HTTPException(422, "Each role (Speaker 1, Speaker 2, Researcher) can be assigned to only one participant.")
    request_id = "SASTRA-" + uuid.uuid4().hex[:10].upper()
    try:  # the unique index on lower(university) rejects duplicates, even under concurrent submits
        sb.table("registrations").insert({"request_id": request_id, "university": payload.university.strip(), "country": payload.country.strip(), "coach_name": payload.coach_name.strip(), "coach_email": str(payload.coach_email), "coach_phone": payload.coach_phone.strip()}).execute()
    except APIError as e:
        if e.code == "23505": raise HTTPException(409, "This university already has a team registration.")
        raise
    try:
        sb.table("participants").insert([{"request_id": request_id, "position": i + 1, "name": p.name, "email": str(p.email), "year": p.year, "role": p.role} for i, p in enumerate(payload.participants)]).execute()
    except Exception:
        sb.table("registrations").delete().eq("request_id", request_id).execute()  # no half-saved teams
        raise
    log_audit(request_id, str(payload.coach_email), "registration_submitted", "", "REVIEW_PENDING", f"university={payload.university}; country={payload.country}")
    send_status_email(request_id, *received_email(payload.coach_name, payload.university.strip()), addresses(str(payload.coach_email), [str(p.email) for p in payload.participants]))
    return {"request_id":request_id, "status":"REVIEW_PENDING", "message":"Registration submitted for review."}

def fetch_registrations(status: str = "ALL"):
    q = sb.table("registrations").select("*, participants(*)").order("created_at", desc=True)
    if status != "ALL": q = q.eq("status", status)
    return [flatten(r) for r in q.execute().data]

@app.get("/api/admin/registrations")
def list_registrations(status: str = Query(default="ALL"), admin=Depends(require_admin)):
    rows = fetch_registrations(status)
    return {"items":rows, "total":len(rows)}

LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz"  # no I, O, l, o: easy to misread in an email
TEAM_EMAIL_DOMAIN = os.getenv("TEAM_EMAIL_DOMAIN", "teams.icac.invalid")

def team_email(request_id):
    """Hidden Supabase Auth identifier. Teams sign in with their Request ID; the portal adds this suffix."""
    return f"{request_id.lower()}@{TEAM_EMAIL_DOMAIN}"

def new_password():
    """10 characters: 4 letters + 6 digits, shuffled."""
    chars = [secrets.choice(LETTERS) for _ in range(4)] + [secrets.choice(string.digits) for _ in range(6)]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)

def team_recipients(request_id, coach_email):
    parts = sb.table("participants").select("email").eq("request_id", request_id).order("position").execute().data
    return addresses(coach_email, [p["email"] for p in parts])

def code_taken(code, own_id=None):
    rows = sb.table("teams").select("request_id,team_code").not_.is_("team_code", "null").execute().data
    return any(r["team_code"].lower() == code.lower() and r["request_id"] != own_id for r in rows)

def one(x):
    """PostgREST returns a to-one embed as an object (or null) and a to-many embed as a list."""
    return (x[0] if x else {}) if isinstance(x, list) else (x or {})

@app.post("/api/admin/registrations/{request_id}/decision")
def decide(request_id: str, payload: DecisionIn, admin=Depends(require_admin)):
    decision = payload.decision.upper()
    if decision not in ("APPROVED", "REJECTED"): raise HTTPException(422, "Decision must be APPROVED or REJECTED")
    note, code = payload.note.strip(), payload.team_code.strip() or None
    if decision == "APPROVED" and code and code_taken(code): raise HTTPException(409, f"Team code '{code}' is already used by another team.")
    # Conditional update = atomic: two admins clicking at once can't both decide.
    done = sb.table("registrations").update({"status":decision, "decision_at":now(), "decision_by":admin["email"], "decision_note":note}).eq("request_id", request_id).eq("status", "REVIEW_PENDING").execute().data
    if not done:
        exists = sb.table("registrations").select("request_id").eq("request_id", request_id).execute().data
        raise HTTPException(409, "This registration already has a final decision") if exists else HTTPException(404, "Request ID not found")
    coach, university = done[0]["coach_name"], done[0]["university"]
    recipients = team_recipients(request_id, done[0]["coach_email"])
    if decision == "REJECTED":
        log_audit(request_id, admin["email"], "admin_decision", "REVIEW_PENDING", decision, note)
        return {"request_id":request_id, "status":decision, "email":send_status_email(request_id, *rejection_email(coach, university, note), recipients)}
    # Selected: create the team's login (Supabase Auth hashes the password) and its team row.
    password = new_password()
    try:
        uid = sb.auth.admin.create_user({"email": team_email(request_id), "password": password, "email_confirm": True}).user.id
        try: sb.table("teams").insert({"request_id": request_id, "user_id": uid, "team_code": code}).execute()
        except Exception:
            sb.auth.admin.delete_user(uid); raise
    except Exception as exc:
        logging.exception("Could not create team login for %s", request_id)
        sb.table("registrations").update({"status":"REVIEW_PENDING", "decision_at":None, "decision_by":None, "decision_note":None}).eq("request_id", request_id).execute()  # undo: stays pending
        raise HTTPException(502, f"Could not create the team's login, so nothing was changed. Please try again. ({str(exc)[:160]})")
    log_audit(request_id, admin["email"], "admin_decision", "REVIEW_PENDING", decision, note)
    log_audit(request_id, admin["email"], "team_account_created", details=f"team_code={code or '-'}")
    return {"request_id":request_id, "status":decision, "team_code":code, "email":send_status_email(request_id, *selection_email(coach, university, request_id, password, code, note), recipients)}

# ---- Team management (selected teams) ----
def team_row(request_id):
    rows = sb.table("teams").select("*").eq("request_id", request_id).limit(1).execute().data
    if not rows: raise HTTPException(404, "Team not found")
    return rows[0]

@app.get("/api/admin/teams")
def list_teams(admin=Depends(require_admin)):
    rows = sb.table("teams").select("*, registrations(university,country,coach_name,coach_email), clarification_questions(id), memorial_files(id)").order("created_at").execute().data
    return {"items": [{"request_id": t["request_id"], "team_code": t["team_code"], "round_status": t["round_status"], "clarification_edits_used": t["clarification_edits_used"], "created_at": t["created_at"], **one(t["registrations"]), "questions": len(t["clarification_questions"]), "files": len(t["memorial_files"])} for t in rows]}

@app.get("/api/admin/teams/{request_id}")
def team_detail(request_id: str, admin=Depends(require_admin)):
    rows = sb.table("teams").select("*, registrations(*, participants(*)), clarification_questions(*), memorial_files(*), messages(*)").eq("request_id", request_id).limit(1).execute().data
    if not rows: raise HTTPException(404, "Team not found")
    t = rows[0]; reg = one(t.pop("registrations")); t.pop("user_id", None)
    reg["participants"] = sorted(reg.get("participants", []), key=lambda p: p["position"])
    t["registration"] = reg
    t["clarification_questions"].sort(key=lambda q: q["position"]); t["memorial_files"].sort(key=lambda f: f["slot"]); t["messages"].sort(key=lambda m: m["sent_at"], reverse=True)
    return t

@app.patch("/api/admin/teams/{request_id}")
def update_team(request_id: str, payload: TeamPatch, admin=Depends(require_admin)):
    upd = {}
    if payload.team_code is not None:
        code = payload.team_code.strip() or None
        if code and code_taken(code, request_id): raise HTTPException(409, f"Team code '{code}' is already used by another team.")
        upd["team_code"] = code
    if payload.round_status: upd["round_status"] = payload.round_status
    if not upd: raise HTTPException(422, "Nothing to update")
    if not sb.table("teams").update(upd).eq("request_id", request_id).execute().data: raise HTTPException(404, "Team not found")
    log_audit(request_id, admin["email"], "team_updated", details="; ".join(f"{k}={v}" for k, v in upd.items()))
    return upd

def team_coach(request_id):
    return sb.table("registrations").select("coach_name,coach_email").eq("request_id", request_id).execute().data[0]

@app.post("/api/admin/teams/{request_id}/reset-password")
def reset_team_password(request_id: str, admin=Depends(require_admin)):
    team = team_row(request_id)
    if not team["user_id"]: raise HTTPException(409, "This team has no login account")
    coach, password = team_coach(request_id), new_password()
    sb.auth.admin.update_user_by_id(team["user_id"], {"password": password})
    sb.table("teams").update({"must_change_password": True}).eq("request_id", request_id).execute()
    log_audit(request_id, admin["email"], "team_password_reset")
    return {"email": send_status_email(request_id, *password_reset_email(coach["coach_name"], request_id, password), team_recipients(request_id, coach["coach_email"]))}

@app.post("/api/admin/teams/{request_id}/messages")
def send_team_message(request_id: str, payload: MessageIn, admin=Depends(require_admin)):
    team_row(request_id)
    text = payload.body.strip()
    if not text: raise HTTPException(422, "Message cannot be empty")
    coach = team_coach(request_id)
    sb.table("messages").insert({"request_id": request_id, "sender": admin["email"], "body": text}).execute()
    log_audit(request_id, admin["email"], "message_sent", details=text[:200])
    return {"email": send_status_email(request_id, *message_email(coach["coach_name"], text), team_recipients(request_id, coach["coach_email"]))}

@app.get("/api/admin/audit/{request_id}")
def audit_trail(request_id: str, admin=Depends(require_admin)):
    events = sb.table("audit_log").select("timestamp:at, request_id, actor, action, from_status, to_status, details").eq("request_id", request_id).order("at").execute().data
    return {"request_id":request_id, "events":events}

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

def xlsx_response(cols, rows, filename):
    wb = Workbook(); ws = wb.active; ws.append(cols)
    for r in rows:
        ws.append(r)
        for c in ws[ws.max_row]:  # user-typed text starting with = + - @ must stay text, never become a spreadsheet formula
            if isinstance(c.value, str) and c.value[:1] in ("=", "+", "-", "@", "\t", "\r"): c.data_type = "s"
    buffer = BytesIO(); wb.save(buffer); buffer.seek(0)
    return StreamingResponse(buffer, media_type=XLSX, headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.get("/api/admin/export.xlsx")
def export_xlsx(admin=Depends(require_admin)):
    cols = ["request_id", "created_at", "status", "university", "country", "coach_name", "coach_email", "coach_phone"] + [f"participant{i}_{f}" for i in (1, 2, 3) for f in ("name", "email", "year", "role")] + ["decision_at", "decision_by", "decision_note"]
    return xlsx_response(cols, [[r.get(c) for c in cols] for r in fetch_registrations()], "sastra-registrations.xlsx")

@app.get("/api/admin/export/participants.xlsx")
def export_participants(admin=Depends(require_admin)):
    regs = sb.table("registrations").select("*, participants(*), teams(team_code)").order("created_at").execute().data
    rows = [[r["request_id"], one(r.get("teams")).get("team_code"), r["status"], r["university"], r["country"], r["coach_name"], r["coach_email"], r["coach_phone"], p["position"], p["name"], p["email"], p["year"], p["role"]]
            for r in regs for p in sorted(r["participants"], key=lambda p: p["position"])]
    return xlsx_response(["Request ID", "Team code", "Registration status", "University", "Country", "Coach name", "Coach email", "Coach phone", "Participant no.", "Name", "Email", "Year / course", "Role"], rows, "sastra-participants.xlsx")

@app.get("/api/admin/export/clarifications.xlsx")
def export_clarifications(admin=Depends(require_admin)):
    qs = sb.table("clarification_questions").select("request_id, position, question, created_at, updated_at, teams(team_code, registrations(university, country))").order("request_id").order("position").execute().data
    rows = []
    for q in qs:
        t = one(q.get("teams")); reg = one(t.get("registrations"))
        rows.append([t.get("team_code"), q["request_id"], reg.get("university"), reg.get("country"), q["position"], q["question"], q["created_at"], q["updated_at"]])
    rows.sort(key=lambda r: (str(r[2] or ""), r[1], r[4]))
    return xlsx_response(["Team code", "Request ID", "University", "Country", "Question no.", "Question", "Submitted", "Last edited"], rows, "sastra-clarification-questions.xlsx")


# ---- Site content: published documents, announcements, schedule (site_content table + Storage bucket) ----
MAX_PDF = 4 * 1024 * 1024  # ponytail: Vercel rejects request bodies >4.5 MB; larger PDFs need browser->Storage signed uploads

def read_site(): return {r["key"]: r["value"] for r in sb.table("site_content").select("key,value").execute().data}
def write_section(key, value): sb.table("site_content").upsert({"key": key, "value": value, "updated_at": now()}).execute()
def public_url(path): return sb.storage.from_(BUCKET).get_public_url(path)
def put_pdf(path, data): sb.storage.from_(BUCKET).upload(path, data, {"content-type": "application/pdf", "upsert": "true", "cache-control": "60"})
def drop_pdfs(paths):
    if paths: sb.storage.from_(BUCKET).remove(paths)

class AnnouncementIn(BaseModel):
    date: str = Field(max_length=40); title: str = Field(min_length=1, max_length=200); body: str = Field(default="", max_length=2000)
    file: Optional[str] = Field(default=None, pattern=r"^att-[0-9a-f]{32}\.pdf$")
class ScheduleIn(BaseModel):
    date: str = Field(min_length=1, max_length=60); title: str = Field(min_length=1, max_length=200); note: str = Field(default="", max_length=500)
class FaqIn(BaseModel):
    q: str = Field(min_length=1, max_length=300); a: str = Field(min_length=1, max_length=3000)
class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=100); role: str = Field(default="", max_length=100); phone: str = Field(default="", max_length=30)
class PrizeRow(BaseModel):
    category: str = Field(min_length=1, max_length=200); amount: str = Field(min_length=1, max_length=60)
class PrizesIn(BaseModel):
    total: str = Field(min_length=1, max_length=60); rows: list[PrizeRow]
SECTIONS = {"announcements": list[AnnouncementIn], "schedule": list[ScheduleIn], "faqs": list[FaqIn], "contacts": list[ContactIn], "prizes": PrizesIn}

@app.get("/api/site")
def site_content(): return read_site()

@app.get("/api/files/{key}")
def get_file(key: str):
    doc = read_site().get("documents", {}).get(key)
    if not doc or not doc.get("file"): raise HTTPException(404, "Not published")
    return RedirectResponse(public_url(doc["file"]))

def check_pdf(data: bytes):
    if not data.startswith(b"%PDF"): raise HTTPException(400, "Only PDF files are accepted")
    if len(data) > MAX_PDF: raise HTTPException(413, "PDF must be 4 MB or smaller")

@app.put("/api/admin/documents/{key}")
async def upload_document(key: str, request: Request, admin=Depends(require_admin)):
    docs = read_site().get("documents", {})
    if key not in docs: raise HTTPException(404, "Unknown document")
    data = await request.body(); check_pdf(data)
    put_pdf(f"{key}.pdf", data)
    docs[key].update(file=f"{key}.pdf", updated=now()); write_section("documents", docs)
    log_audit("SITE", admin["email"], "DOCUMENT_PUBLISHED", details=f"{key} ({len(data)//1024} KB)")
    return docs[key]

@app.delete("/api/admin/documents/{key}")
def unpublish_document(key: str, admin=Depends(require_admin)):
    docs = read_site().get("documents", {})
    if key not in docs: raise HTTPException(404, "Unknown document")
    drop_pdfs([f"{key}.pdf"])
    docs[key].update(file=None, updated=None); write_section("documents", docs)
    log_audit("SITE", admin["email"], "DOCUMENT_REMOVED", details=key)
    return docs[key]

@app.put("/api/admin/attachments")
async def upload_attachment(request: Request, admin=Depends(require_admin)):
    data = await request.body(); check_pdf(data)
    name = f"att-{uuid.uuid4().hex}.pdf"; put_pdf(name, data)
    log_audit("SITE", admin["email"], "ATTACHMENT_UPLOADED", details=f"{name} ({len(data)//1024} KB)")
    return {"file": name}

@app.get("/api/attachments/{name}")
def get_attachment(name: str):
    if not re.fullmatch(r"att-[0-9a-f]{32}\.pdf", name): raise HTTPException(404, "Not found")
    return RedirectResponse(public_url(name))

@app.put("/api/admin/content/{section}")
async def set_content(section: str, request: Request, admin=Depends(require_admin)):
    model = SECTIONS.get(section)
    if not model: raise HTTPException(404, "Unknown section")
    ta = TypeAdapter(model)
    try: value = ta.dump_python(ta.validate_python(await request.json()))
    except ValidationError as e: raise HTTPException(422, "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:3]))
    write_section(section, value)
    if section == "announcements":  # drop attachments no announcement references any more
        used = {a["file"] for a in value if a.get("file")}
        stored = [o["name"] for o in sb.storage.from_(BUCKET).list() if o["name"].startswith("att-")]
        drop_pdfs([n for n in stored if n not in used])
    log_audit("SITE", admin["email"], f"{section.upper()}_UPDATED")
    return value


# ---- Admin: download a team's memorial file ----
MEMORIALS = "memorials"  # private bucket

@app.get("/api/admin/teams/{request_id}/files/{slot}/link")
def memorial_link(request_id: str, slot: int, admin=Depends(require_admin)):
    rows = sb.table("memorial_files").select("storage_path,file_name").eq("request_id", request_id).eq("slot", slot).limit(1).execute().data
    if not rows: raise HTTPException(404, "File not found")
    bucket = sb.storage.from_(MEMORIALS)
    try: res = bucket.create_signed_url(rows[0]["storage_path"], 60, {"download": rows[0]["file_name"]})
    except TypeError: res = bucket.create_signed_url(rows[0]["storage_path"], 60)
    url = res.get("signedURL") or res.get("signedUrl")
    if url and not url.startswith("http"): url = os.environ["SUPABASE_URL"].rstrip("/") + "/storage/v1" + url
    log_audit(request_id, admin["email"], "memorial_file_downloaded", details=f"slot {slot}: {rows[0]['file_name']}")
    return {"url": url, "name": rows[0]["file_name"]}


# ---- Participant portal: a team signs in with Supabase Auth (User ID = its Request ID) ----
MAX_FILE, MAX_EDITS = 2 * 1024 * 1024, 4
SLOT_KIND = {1: "pdf", 2: "pdf", 3: "doc", 4: "doc"}   # 2 PDFs + 2 Word documents
DOC_TYPES = {".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK\x03\x04"), ".doc": ("application/msword", b"\xd0\xcf\x11\xe0")}

def require_team(authorization: Optional[str] = Header(default=None)):
    token = bearer(authorization)
    uid = cached(("user", token), lambda: verified_user_id(token))   # only the identity is cached; the team row (edit counter, password flag) is always read fresh
    rows = sb.table("teams").select("*").eq("user_id", uid).limit(1).execute().data
    if not rows: raise HTTPException(403, "This account is not a team account")
    return rows[0]

def require_ready_team(team=Depends(require_team)):
    if team["must_change_password"]: raise HTTPException(403, "Please change your temporary password first.")
    return team

def stage_open(doc):  # a stage opens when the organisers publish its document under Site content
    return bool(read_site().get("documents", {}).get(doc, {}).get("file"))

@app.get("/api/team/me")
def team_me(team=Depends(require_team)):
    rid = team["request_id"]
    reg = sb.table("registrations").select("university,country,coach_name,coach_email,coach_phone,participants(*)").eq("request_id", rid).limit(1).execute().data[0]
    reg["participants"] = sorted(reg["participants"], key=lambda p: p["position"])
    return {"request_id": rid, "team_code": team["team_code"], "must_change_password": team["must_change_password"], "round_status": team["round_status"], "registration": reg,
            "clarifications_open": stage_open("proposition"), "memorial_open": stage_open("memorial"), "edits_used": team["clarification_edits_used"], "max_edits": MAX_EDITS,
            "questions": sb.table("clarification_questions").select("position,question,updated_at").eq("request_id", rid).order("position").execute().data,
            "files": sb.table("memorial_files").select("slot,kind,file_name,size_bytes,uploaded_at").eq("request_id", rid).order("slot").execute().data,
            "messages": sb.table("messages").select("id,body,sent_at").eq("request_id", rid).order("sent_at", desc=True).execute().data}

@app.post("/api/team/password")
def team_password(payload: PasswordIn, team=Depends(require_team)):
    pw = payload.new_password
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)): raise HTTPException(422, "Password must contain at least one letter and one digit.")
    sb.auth.admin.update_user_by_id(team["user_id"], {"password": pw})
    sb.table("teams").update({"must_change_password": False}).eq("request_id", team["request_id"]).execute()
    log_audit(team["request_id"], team["request_id"], "team_password_changed")
    return {"ok": True}

@app.put("/api/team/questions")
def save_questions(payload: QuestionsIn, team=Depends(require_ready_team)):
    if not stage_open("proposition"): raise HTTPException(403, "Clarification questions open once the moot proposition is released.")
    new = [q.strip() for q in payload.questions]
    if any(not q or len(q) > 1000 for q in new): raise HTTPException(422, "Each question must be between 1 and 1000 characters.")
    rid, used = team["request_id"], team["clarification_edits_used"]
    old = sb.table("clarification_questions").select("position,question").eq("request_id", rid).order("position").execute().data
    if [o["question"] for o in old] == new: return {"saved": False, "edits_used": used}   # nothing changed: no edit is spent
    if old:  # the first save is free; every later change spends one of the 4 edits
        if used >= MAX_EDITS: raise HTTPException(403, f"You have used all {MAX_EDITS} edits of your clarification questions.")
        if not sb.table("teams").update({"clarification_edits_used": used + 1}).eq("request_id", rid).eq("clarification_edits_used", used).execute().data:
            raise HTTPException(409, "Your questions were changed in another window. Reload the page and try again.")
        used += 1
    before = {o["position"]: o["question"] for o in old}
    changed = [{"request_id": rid, "position": i + 1, "question": q, "updated_at": now()} for i, q in enumerate(new) if before.get(i + 1) != q]
    if changed: sb.table("clarification_questions").upsert(changed, on_conflict="request_id,position").execute()
    if len(old) > len(new): sb.table("clarification_questions").delete().eq("request_id", rid).gt("position", len(new)).execute()
    log_audit(rid, rid, "clarification_questions_saved", details=f"{len(new)} questions; edits used {used}/{MAX_EDITS}")
    return {"saved": True, "edits_used": used}

@app.put("/api/team/memorial/{slot}")
async def upload_memorial(slot: int, request: Request, team=Depends(require_ready_team)):
    kind = SLOT_KIND.get(slot)
    if not kind: raise HTTPException(404, "Unknown slot")
    if not stage_open("memorial"): raise HTTPException(403, "Memorial submission has not opened yet.")
    data = await request.body()
    if not data: raise HTTPException(400, "The file is empty.")
    if len(data) > MAX_FILE: raise HTTPException(413, "Each file must be 2 MB or smaller.")
    name = unquote(request.headers.get("x-file-name", "")).replace("\\", "/").split("/")[-1].strip()[:120] or f"slot-{slot}"
    ext = os.path.splitext(name)[1].lower()
    if kind == "pdf":
        if ext != ".pdf" or not data.startswith(b"%PDF"): raise HTTPException(400, "Slots 1 and 2 accept PDF files only.")
        ctype = "application/pdf"
    else:
        doc = DOC_TYPES.get(ext)
        if not doc or not data.startswith(doc[1]): raise HTTPException(400, "Slots 3 and 4 accept Word documents (.doc or .docx) only.")
        ctype = doc[0]
    rid = team["request_id"]; path = f"{rid}/slot{slot}-{uuid.uuid4().hex[:8]}{ext}"
    bucket = sb.storage.from_(MEMORIALS)
    bucket.upload(path, data, {"content-type": ctype})
    old = sb.table("memorial_files").select("storage_path").eq("request_id", rid).eq("slot", slot).execute().data
    try: sb.table("memorial_files").upsert({"request_id": rid, "slot": slot, "kind": kind, "file_name": name, "storage_path": path, "size_bytes": len(data), "uploaded_at": now()}, on_conflict="request_id,slot").execute()
    except Exception:
        bucket.remove([path]); raise   # don't leave an orphan file behind
    if old: bucket.remove([old[0]["storage_path"]])
    log_audit(rid, rid, "memorial_file_uploaded", details=f"slot {slot}: {name} ({len(data)//1024} KB)")
    return {"slot": slot, "file_name": name, "size_bytes": len(data)}

@app.delete("/api/team/memorial/{slot}")
def delete_memorial(slot: int, team=Depends(require_ready_team)):
    if slot not in SLOT_KIND: raise HTTPException(404, "Unknown slot")
    if not stage_open("memorial"): raise HTTPException(403, "Memorial submission has not opened yet.")
    rid = team["request_id"]
    old = sb.table("memorial_files").select("storage_path,file_name").eq("request_id", rid).eq("slot", slot).execute().data
    if not old: raise HTTPException(404, "No file in this slot")
    sb.table("memorial_files").delete().eq("request_id", rid).eq("slot", slot).execute()
    sb.storage.from_(MEMORIALS).remove([old[0]["storage_path"]])
    log_audit(rid, rid, "memorial_file_removed", details=f"slot {slot}: {old[0]['file_name']}")
    return {"ok": True}
