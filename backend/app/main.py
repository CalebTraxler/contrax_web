import json
from typing import Optional
import logging
import re
import threading
import uuid

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import analyzer, db, payments
from .config import REPO_DIR, UPLOADS_DIR, settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("contrax")

app = FastAPI(title="Contrax API")
db.init_db()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
TRADES = {"plumbing", "hvac", "roofing", "electrical", "other"}


def _run_analysis(report_id: str):
    row = db.get_report(report_id)
    if not row or row["status"] not in ("queued", "processing"):
        return
    db.update_report(report_id, status="processing")
    file_bytes = None
    if row["file_name"]:
        path = UPLOADS_DIR / report_id
        if path.exists():
            file_bytes = path.read_bytes()
    try:
        report = analyzer.analyze(
            file_bytes, row["file_mime"], row["quote_text"], row["zip_code"], row["trade"]
        )
        db.set_report_result(report_id, report)
        log.info("report %s complete", report_id)
    except Exception as e:
        log.exception("report %s failed", report_id)
        db.set_report_failed(report_id, str(e))


def _start_analysis(report_id: str):
    db.update_report(report_id, status="queued")
    threading.Thread(target=_run_analysis, args=(report_id,), daemon=True).start()


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "mock_analysis": settings.mock_analysis,
        "skip_payments": settings.skip_payments,
        "anthropic_configured": bool(settings.anthropic_api_key),
        "stripe_configured": bool(settings.stripe_secret_key),
    }


@app.post("/api/waitlist")
def waitlist(payload: dict):
    email = (payload.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Invalid email address")
    db.add_waitlist(email)
    return {"ok": True}


@app.post("/api/quotes")
async def create_quote(
    zip_code: str = Form(...),
    trade: str = Form(...),
    email: str = Form(""),
    quote_text: str = Form(""),
    file: Optional[UploadFile] = None,
):
    zip_code = zip_code.strip()
    if not re.match(r"^\d{5}$", zip_code):
        raise HTTPException(422, "zip_code must be a 5-digit US zip")
    if trade not in TRADES:
        raise HTTPException(422, f"trade must be one of {sorted(TRADES)}")
    email = email.strip().lower()
    if email and not EMAIL_RE.match(email):
        raise HTTPException(422, "Invalid email address")

    file_bytes = await file.read() if file else None
    if file_bytes and len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (20 MB max)")
    if not file_bytes and not quote_text.strip():
        raise HTTPException(422, "Provide a quote file or pasted quote text")

    report_id = uuid.uuid4().hex
    if file_bytes:
        (UPLOADS_DIR / report_id).write_bytes(file_bytes)
    db.create_report(
        report_id, email or None, zip_code, trade,
        quote_text.strip() or None,
        file.filename if file else None,
        file.content_type if file else None,
        status="pending_payment",
    )

    if settings.skip_payments:
        _start_analysis(report_id)
        return {"report_id": report_id, "status": "queued", "checkout_url": None}

    try:
        checkout_url = payments.create_checkout(report_id, email or None)
    except payments.PaymentsError as e:
        raise HTTPException(503, str(e))
    return {"report_id": report_id, "status": "pending_payment", "checkout_url": checkout_url}


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = payments.verify_webhook(payload, sig)
    except payments.PaymentsError as e:
        raise HTTPException(400, str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        report_id = (session.get("metadata") or {}).get("report_id")
        row = db.get_report(report_id) if report_id else None
        if row and row["status"] == "pending_payment":
            db.update_report(report_id, paid_at=db.now(), stripe_session_id=session.get("id"))
            _start_analysis(report_id)
            log.info("report %s paid via %s", report_id, session.get("id"))
    return {"received": True}


@app.get("/api/reports/{report_id}")
def get_report(report_id: str):
    row = db.get_report(report_id)
    if not row:
        raise HTTPException(404, "Report not found")
    out = {
        "report_id": row["id"],
        "status": row["status"],
        "zip_code": row["zip_code"],
        "trade": row["trade"],
        "created_at": row["created_at"],
    }
    if row["status"] == "complete" and row["report_json"]:
        report = json.loads(row["report_json"])
        report.pop("extraction", None)
        out["report"] = report
    if row["status"] == "failed":
        out["error"] = "Analysis failed. You have not been charged for a failed report — contact support."
    return JSONResponse(out)


# Static frontend — mounted last so /api/* wins.
app.mount("/", StaticFiles(directory=REPO_DIR, html=True), name="site")
