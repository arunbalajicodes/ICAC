from __future__ import annotations
import json, os, re, smtplib, uuid, logging
from datetime import datetime
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Literal, Optional
from fastapi import Depends, FastAPI, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
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

def require_admin(authorization: Optional[str] = Header(default=None)):
    """Supabase Auth proves who you are (JWT); the profiles table decides if you're an active admin."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Admin sign-in required")
    try: user = sb.auth.get_user(authorization.split(" ", 1)[1]).user
    except Exception: raise HTTPException(401, "Admin session expired; sign in again")
    if not user: raise HTTPException(401, "Admin session expired; sign in again")
    rows = sb.table("profiles").select("email,display_name,role,active").eq("id", user.id).limit(1).execute().data
    if not rows or rows[0]["role"] != "admin" or not rows[0]["active"]:
        raise HTTPException(403, "This account is not an active admin")
    return {"email": rows[0]["email"], "display_name": rows[0]["display_name"] or rows[0]["email"]}

@app.get("/api/health")
def health(): return {"ok": True, "event": CONFIG["event_name"]}

@app.get("/api/config")
def public_config():
    current = datetime.now(TZ)
    opens, closes = parse_time("registration_open"), parse_time("registration_close")
    return {"event_name":CONFIG["event_name"], "event_start":CONFIG["event_start"], "event_end":CONFIG["event_end"], "registration_open":CONFIG["registration_open"], "registration_close":CONFIG["registration_close"], "registration_open_now":opens <= current <= closes, "timezone":CONFIG.get("timezone"), "max_participants_per_team":CONFIG.get("max_participants_per_team",3), "email_test_mode":os.getenv("EMAIL_TEST_MODE","true").lower()=="true"}

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
    send_status_email(request_id, "Registration received — SASTRA Moot Court", f"Dear {payload.coach_name},\n\nYour team registration for {CONFIG['event_name']} has been received and is pending admin review. We will send another email when a decision is made.", str(payload.coach_email))
    return {"request_id":request_id, "status":"REVIEW_PENDING", "message":"Registration submitted for review."}

def fetch_registrations(status: str = "ALL"):
    q = sb.table("registrations").select("*, participants(*)").order("created_at", desc=True)
    if status != "ALL": q = q.eq("status", status)
    return [flatten(r) for r in q.execute().data]

@app.get("/api/admin/registrations")
def list_registrations(status: str = Query(default="ALL"), admin=Depends(require_admin)):
    rows = fetch_registrations(status)
    return {"items":rows, "total":len(rows)}

@app.post("/api/admin/registrations/{request_id}/decision")
def decide(request_id: str, payload: DecisionIn, admin=Depends(require_admin)):
    decision = payload.decision.upper()
    if decision not in ("APPROVED", "REJECTED"): raise HTTPException(422, "Decision must be APPROVED or REJECTED")
    # Conditional update = atomic: two admins clicking at once can't both decide.
    done = sb.table("registrations").update({"status":decision, "decision_at":now(), "decision_by":admin["email"], "decision_note":payload.note.strip()}).eq("request_id", request_id).eq("status", "REVIEW_PENDING").execute().data
    if not done:
        exists = sb.table("registrations").select("request_id").eq("request_id", request_id).execute().data
        raise HTTPException(409, "This registration already has a final decision") if exists else HTTPException(404, "Request ID not found")
    log_audit(request_id, admin["email"], "admin_decision", "REVIEW_PENDING", decision, payload.note.strip())
    send_status_email(request_id, f"Registration {decision.lower()} — SASTRA Moot Court", f"Your team registration for {CONFIG['event_name']} has been {decision.lower()}.\n\nAdmin note: {payload.note.strip() or 'No additional note provided.'}", done[0]["coach_email"])
    return {"request_id":request_id, "status":decision}

@app.get("/api/admin/audit/{request_id}")
def audit_trail(request_id: str, admin=Depends(require_admin)):
    events = sb.table("audit_log").select("timestamp:at, request_id, actor, action, from_status, to_status, details").eq("request_id", request_id).order("at").execute().data
    return {"request_id":request_id, "events":events}

@app.get("/api/admin/export.xlsx")
def export_xlsx(admin=Depends(require_admin)):
    cols = ["request_id", "created_at", "status", "university", "country", "coach_name", "coach_email", "coach_phone"] + [f"participant{i}_{f}" for i in (1, 2, 3) for f in ("name", "email", "year", "role")] + ["decision_at", "decision_by", "decision_note"]
    wb = Workbook(); ws = wb.active; ws.append(cols)
    for r in fetch_registrations(): ws.append([r.get(c) for c in cols])
    buffer = BytesIO(); wb.save(buffer); buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition":"attachment; filename=sastra-registrations.xlsx"})


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
