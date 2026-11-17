"""One-off: copy the old Excel data and config/site.json into Supabase.
Run from backend/:  python scripts/import_legacy.py            (everything)
                    python scripts/import_legacy.py --site-only (skip registrations/audit, e.g. if they were test data)
Safe to re-run: rows are upserted, so nothing is duplicated.
"""
import json, os, sys
from pathlib import Path
from dotenv import load_dotenv
from openpyxl import load_workbook
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

def rows(name):
    ws = load_workbook(ROOT / "data" / f"{name}.xlsx", data_only=True).active
    head = [c.value for c in ws[1]]
    return [dict(zip(head, r)) for r in ws.iter_rows(min_row=2, values_only=True) if any(v is not None for v in r)]

def blank(v): return None if v in (None, "") else v

site = json.loads((ROOT / "config" / "site.json").read_text(encoding="utf-8"))
sb.table("site_content").upsert([{"key": k, "value": v} for k, v in site.items()]).execute()
print(f"site_content: {len(site)} sections")

if "--site-only" not in sys.argv:
    regs, parts = [], []
    for r in rows("registrations"):
        regs.append({k: blank(r[k]) for k in ("request_id", "created_at", "status", "university", "country", "coach_name", "coach_email", "coach_phone", "decision_at", "decision_by", "decision_note")})
        for i in (1, 2, 3):
            if r.get(f"participant{i}_name"):
                parts.append({"request_id": r["request_id"], "position": i, "name": r[f"participant{i}_name"], "email": r[f"participant{i}_email"], "year": r[f"participant{i}_year"]})
    if regs:
        sb.table("registrations").upsert(regs).execute()
        sb.table("participants").upsert(parts, on_conflict="request_id,position").execute()
    print(f"registrations: {len(regs)}, participants: {len(parts)}")
    # audit_log is append-only with generated ids, so skip it if already imported (avoids duplicates on re-run)
    if not sb.table("audit_log").select("id").limit(1).execute().data:
        audit = [{"at": blank(a["timestamp"]), **{k: blank(a[k]) for k in ("request_id", "actor", "action", "from_status", "to_status", "details")}} for a in rows("audit")]
        if audit: sb.table("audit_log").insert(audit).execute()
        print(f"audit_log: {len(audit)} events")
    else:
        print("audit_log: already has data, skipped")

pdf = ROOT / "config" / "files" / "rules.pdf"
if pdf.exists() and site["documents"]["rules"].get("file"):
    sb.storage.from_("site-files").upload("rules.pdf", pdf.read_bytes(), {"content-type": "application/pdf", "upsert": "true"})
    print("storage: rules.pdf uploaded")
