from __future__ import annotations
import json, os, secrets, smtplib, threading, uuid, logging
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from openpyxl import Workbook, load_workbook
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "data"
if os.getenv("VERCEL"):  # ponytail: /tmp is ephemeral on Vercel; swap in a real DB for persistence
    import shutil
    DATA = Path("/tmp/data"); shutil.copytree(BASE.parent / "data", DATA, dirs_exist_ok=True)
DATA.mkdir(exist_ok=True)
load_dotenv(BASE.parent / ".env")
with open(BASE / "config.json", encoding="utf-8") as f:
    CONFIG = json.load(f)
TZ = ZoneInfo(CONFIG.get("timezone", "Asia/Kolkata"))
LOCK = threading.RLock()
REG_FILE, ADMIN_FILE, AUDIT_FILE = DATA / "registrations.xlsx", DATA / "admins.xlsx", DATA / "audit.xlsx"
REG_HEADERS = ["request_id", "created_at", "status", "university", "country", "coach_name", "coach_email", "coach_phone", "participant1_name", "participant1_email", "participant1_year", "participant2_name", "participant2_email", "participant2_year", "participant3_name", "participant3_email", "participant3_year", "decision_at", "decision_by", "decision_note"]
ADMIN_HEADERS = ["email", "display_name", "active"]
AUDIT_HEADERS = ["timestamp", "request_id", "actor", "action", "from_status", "to_status", "details"]


def init_book(path: Path, headers: list[str], rows=None):
    if not path.exists():
        wb = Workbook(); ws = wb.active; ws.append(headers)
        for row in rows or []: ws.append(row)
        wb.save(path)

init_book(REG_FILE, REG_HEADERS)
# One-time compatibility migration for existing local Excel data.
with LOCK:
    _wb = load_workbook(REG_FILE)
    _ws = _wb.active
    _headers = [c.value for c in _ws[1]]
    if "team_name" in _headers:
        _drop = _headers.index("team_name") + 1
        _ws.delete_cols(_drop)
        _wb.save(REG_FILE)
init_book(ADMIN_FILE, ADMIN_HEADERS, [["raghav.kartik2005@gmail.com", "Raghav (demo admin)", True]])
init_book(AUDIT_FILE, AUDIT_HEADERS)

app = FastAPI(title="SASTRA Moot Registration API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class Participant(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    year: str = Field(min_length=1, max_length=40)

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


def now(): return datetime.now(TZ).isoformat(timespec="seconds")
def parse_time(key): return datetime.fromisoformat(CONFIG[key]).replace(tzinfo=TZ)
def get_rows(path):
    wb = load_workbook(path, data_only=True); ws = wb.active
    headers = [c.value for c in ws[1]]
    return [dict(zip(headers, row)) for row in ws.iter_rows(min_row=2, values_only=True) if any(v is not None for v in row)]
def append_row(path, headers, row):
    with LOCK:
        wb = load_workbook(path); ws = wb.active
        if ws.max_row == 1 and ws.cell(1,1).value is None: ws.append(headers)
        ws.append([row.get(h, "") for h in headers]); wb.save(path)
def replace_registration(request_id, updates):
    with LOCK:
        wb = load_workbook(REG_FILE); ws = wb.active; headers = [c.value for c in ws[1]]
        for row in range(2, ws.max_row + 1):
            if ws.cell(row, headers.index("request_id") + 1).value == request_id:
                for key, value in updates.items(): ws.cell(row, headers.index(key) + 1, value)
                wb.save(REG_FILE); return dict(zip(headers, [ws.cell(row, i+1).value for i in range(len(headers))]))
    return None

def log_audit(request_id, actor, action, from_status="", to_status="", details=""):
    append_row(AUDIT_FILE, AUDIT_HEADERS, {"timestamp":now(), "request_id":request_id, "actor":actor, "action":action, "from_status":from_status, "to_status":to_status, "details":details})

def send_status_email(request_id, subject, body, user_email=""):
    # Test mode always routes to configured test recipients, never to real registrants.
    test_mode = os.getenv("EMAIL_TEST_MODE", "true").lower() == "true"
    to_addr = os.getenv("TEST_RECIPIENT", "thanosragu2005@gmail.com") if test_mode else (user_email or os.getenv("TEST_RECIPIENT", "thanosragu2005@gmail.com"))
    cc_addr = os.getenv("TEST_CC", "raghav.kartik2005@gmail.com")
    smtp_user, smtp_pass = os.getenv("SMTP_USER", ""), os.getenv("SMTP_APP_PASSWORD", "")
    if not smtp_user or not smtp_pass:
        logging.warning("Email not sent (SMTP not configured). request_id=%s subject=%s", request_id, subject)
        log_audit(request_id, "system", "email_skipped", details="SMTP credentials not configured")
        return
    msg = EmailMessage(); msg["Subject"] = subject; msg["From"] = smtp_user; msg["To"] = to_addr
    if cc_addr: msg["Cc"] = cc_addr
    msg.set_content(body + f"\n\nRequest ID: {request_id}\n")
    try:
        with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587")), timeout=15) as server:
            server.starttls(); server.login(smtp_user, smtp_pass); server.send_message(msg)
        log_audit(request_id, "system", "email_sent", details=f"to={to_addr}; cc={cc_addr}; subject={subject}")
    except Exception as exc:
        logging.exception("SMTP failure for %s", request_id)
        log_audit(request_id, "system", "email_failed", details=str(exc)[:500])

def admin_identity(email: str, password: str):
    if not secrets.compare_digest(password, os.getenv("ADMIN_PASSWORD", "replace-this-demo-password-now")):
        return None
    email = email.strip().lower()
    for row in get_rows(ADMIN_FILE):
        if str(row.get("email", "")).strip().lower() == email and str(row.get("active", "")).lower() in ("true", "1", "yes"):
            return {"email": email, "display_name": row.get("display_name") or email}
    return None

@app.get("/api/health")
def health(): return {"ok": True, "event": CONFIG["event_name"]}

@app.get("/api/config")
def public_config():
    current = datetime.now(TZ)
    opens, closes = parse_time("registration_open"), parse_time("registration_close")
    return {"event_name":CONFIG["event_name"], "event_start":CONFIG["event_start"], "event_end":CONFIG["event_end"], "registration_open":CONFIG["registration_open"], "registration_close":CONFIG["registration_close"], "registration_open_now":opens <= current <= closes, "timezone":CONFIG.get("timezone"), "max_participants_per_team":CONFIG.get("max_participants_per_team",3)}

@app.post("/api/admin/login")
def admin_login(payload: dict):
    identity = admin_identity(str(payload.get("email", "")), str(payload.get("password", "")))
    if not identity: raise HTTPException(401, "Admin credentials are invalid or this email is not active in the Admins sheet.")
    # Demo bearer token is process-local. Replace with signed, expiring sessions for production.
    token = secrets.token_urlsafe(32); TOKENS[token] = identity
    return {"token":token, "admin":identity}

TOKENS = {}
def require_admin(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Admin sign-in required")
    identity = TOKENS.get(authorization.split(" ",1)[1])
    if not identity: raise HTTPException(401, "Admin session expired; sign in again")
    # Re-check admin sheet on every request so deactivated admins lose access.
    if not any(str(r.get("email", "")).lower() == identity["email"] and str(r.get("active", "")).lower() in ("true", "1", "yes") for r in get_rows(ADMIN_FILE)):
        raise HTTPException(403, "Admin access is disabled")
    return identity

@app.post("/api/registrations", status_code=201)
def create_registration(payload: RegistrationIn):
    current = datetime.now(TZ)
    if not (parse_time("registration_open") <= current <= parse_time("registration_close")):
        raise HTTPException(403, "Registration is currently closed.")
    if len(payload.participants) > int(CONFIG.get("max_participants_per_team", 3)):
        raise HTTPException(422, "A team may have at most three participants.")
    with LOCK:
        existing = get_rows(REG_FILE)
        if any(str(r.get("university", "")).strip().casefold() == payload.university.strip().casefold() for r in existing):
            raise HTTPException(409, "This university already has a team registration.")
        request_id = "SASTRA-" + uuid.uuid4().hex[:10].upper()
        row = {"request_id":request_id, "created_at":now(), "status":"REVIEW_PENDING", "university":payload.university.strip(), "country":payload.country.strip(), "coach_name":payload.coach_name.strip(), "coach_email":str(payload.coach_email), "coach_phone":payload.coach_phone.strip()}
        for i in range(3):
            p = payload.participants[i] if i < len(payload.participants) else None
            row[f"participant{i+1}_name"] = p.name if p else ""; row[f"participant{i+1}_email"] = str(p.email) if p else ""; row[f"participant{i+1}_year"] = p.year if p else ""
        append_row(REG_FILE, REG_HEADERS, row)
    log_audit(request_id, str(payload.coach_email), "registration_submitted", "", "REVIEW_PENDING", f"university={payload.university}; country={payload.country}")
    send_status_email(request_id, "Registration received — SASTRA Moot Court", f"Dear {payload.coach_name},\n\nYour team registration for {CONFIG['event_name']} has been received and is pending admin review. We will send another email when a decision is made.", str(payload.coach_email))
    return {"request_id":request_id, "status":"REVIEW_PENDING", "message":"Registration submitted for review."}

@app.get("/api/admin/registrations")
def list_registrations(status: str = Query(default="ALL"), admin=__import__("fastapi").Depends(require_admin)):
    rows = get_rows(REG_FILE)
    if status != "ALL": rows = [r for r in rows if r.get("status") == status]
    rows.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    return {"items":rows, "total":len(rows)}

@app.post("/api/admin/registrations/{request_id}/decision")
def decide(request_id: str, payload: DecisionIn, admin=__import__("fastapi").Depends(require_admin)):
    decision = payload.decision.upper()
    if decision not in ("APPROVED", "REJECTED"): raise HTTPException(422, "Decision must be APPROVED or REJECTED")
    rows = get_rows(REG_FILE); current = next((r for r in rows if r.get("request_id") == request_id), None)
    if not current: raise HTTPException(404, "Request ID not found")
    if current.get("status") != "REVIEW_PENDING": raise HTTPException(409, "This registration already has a final decision")
    updated = replace_registration(request_id, {"status":decision, "decision_at":now(), "decision_by":admin["email"], "decision_note":payload.note.strip()})
    log_audit(request_id, admin["email"], "admin_decision", "REVIEW_PENDING", decision, payload.note.strip())
    send_status_email(request_id, f"Registration {decision.lower()} — SASTRA Moot Court", f"Your team registration for {CONFIG['event_name']} has been {decision.lower()}.\n\nAdmin note: {payload.note.strip() or 'No additional note provided.'}", str(current.get("coach_email", "")))
    return {"request_id":request_id, "status":decision}

@app.get("/api/admin/audit/{request_id}")
def audit_trail(request_id: str, admin=__import__("fastapi").Depends(require_admin)):
    return {"request_id":request_id, "events":[r for r in get_rows(AUDIT_FILE) if r.get("request_id") == request_id]}

@app.get("/api/admin/export.xlsx")
def export_xlsx(admin=__import__("fastapi").Depends(require_admin)):
    from io import BytesIO
    with LOCK:
        wb = load_workbook(REG_FILE); buffer = BytesIO(); wb.save(buffer); buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition":"attachment; filename=sastra-registrations.xlsx"})
