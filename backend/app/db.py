import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    email TEXT,
    zip_code TEXT NOT NULL,
    trade TEXT NOT NULL,
    status TEXT NOT NULL,
    quote_text TEXT,
    file_name TEXT,
    file_mime TEXT,
    stripe_session_id TEXT,
    paid_at TEXT,
    scan_json TEXT,
    report_json TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS waitlist (
    email TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    contractor_reply TEXT NOT NULL,
    response_json TEXT
);
CREATE TABLE IF NOT EXISTS contractors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    trade TEXT NOT NULL,
    city TEXT NOT NULL,
    zip TEXT NOT NULL,
    license_status TEXT NOT NULL,
    license_number TEXT,
    years INTEGER,
    complaints_3yr INTEGER,
    permits_12mo INTEGER,
    quotes_analyzed INTEGER,
    fair_quote_rate INTEGER,
    phone TEXT,
    blurb TEXT,
    featured INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contractor_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    message TEXT
);
"""

SEED_CONTRACTORS = [
    ("reliable-rooter", "Reliable Rooter & Plumbing", "plumbing", "Wichita, KS", "67202", "verified", "KS-P-48211", 14, 0, 37, 61, 92, "(316) 555-0141", "Family-run drain, leak, and water-heater specialists. Itemized quotes as standard.", 1),
    ("prairie-plumbing", "Prairie Plumbing Co.", "plumbing", "Wichita, KS", "67203", "verified", "KS-P-51877", 9, 1, 22, 34, 78, "(316) 555-0178", "Full-service residential plumbing across Sedgwick County.", 0),
    ("wichita-drain-pros", "Wichita Drain Pros", "plumbing", "Wichita, KS", "67214", "verified", "KS-P-60214", 6, 0, 15, 19, 85, "(316) 555-0102", "Drain cleaning and repair. Upfront flat-rate pricing.", 0),
    ("anderson-plumbing", "Anderson Plumbing Co.", "plumbing", "Wichita, KS", "67202", "not_found", None, 3, 2, 4, 12, 41, "(316) 555-0163", "General plumbing repair.", 0),
    ("keystone-hvac", "Keystone Heating & Air", "hvac", "Wichita, KS", "67202", "verified", "KS-M-33902", 11, 0, 41, 27, 88, "(316) 555-0129", "Install and repair for furnaces, AC, and heat pumps. Free second opinions.", 0),
    ("summit-air", "Summit Air Solutions", "hvac", "Wichita, KS", "67203", "verified", "KS-M-41230", 4, 1, 9, 8, 74, "(316) 555-0195", "Residential HVAC service and seasonal tune-ups.", 0),
    ("flint-hills-roofing", "Flint Hills Roofing", "roofing", "Wichita, KS", "67202", "verified", "KS-R-27418", 16, 1, 52, 44, 90, "(316) 555-0117", "Asphalt and metal roofing. Storm-damage inspections documented with photos.", 0),
    ("redbud-roofing", "Redbud Roofing & Exteriors", "roofing", "Wichita, KS", "67214", "not_found", None, 2, 0, 3, 5, 58, "(316) 555-0186", "Roof repair and gutter work.", 0),
    ("sparkline-electric", "Sparkline Electric", "electrical", "Wichita, KS", "67202", "verified", "KS-E-19035", 8, 0, 18, 11, 86, "(316) 555-0150", "Licensed residential electricians. Panel upgrades and EV chargers.", 0),
]


def seed_contractors_if_empty():
    with conn() as c:
        n = c.execute("SELECT COUNT(*) FROM contractors").fetchone()[0]
        if n == 0:
            c.executemany(
                "INSERT INTO contractors (id,name,trade,city,zip,license_status,license_number,years,"
                "complaints_3yr,permits_12mo,quotes_analyzed,fair_quote_rate,phone,blurb,featured)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                SEED_CONTRACTORS,
            )


def list_contractors(zip_prefix: str, trade: str):
    q = "SELECT * FROM contractors WHERE 1=1"
    args = []
    if zip_prefix:
        q += " AND zip LIKE ?"
        args.append(zip_prefix + "%")
    if trade:
        q += " AND trade = ?"
        args.append(trade)
    q += " ORDER BY featured DESC, fair_quote_rate DESC"
    with conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def get_contractor(cid: str):
    with conn() as c:
        row = c.execute("SELECT * FROM contractors WHERE id=?", (cid,)).fetchone()
        return dict(row) if row else None


def add_lead(contractor_id: str, name: str, email: str, message: str):
    with conn() as c:
        c.execute(
            "INSERT INTO leads (contractor_id, created_at, name, email, message) VALUES (?,?,?,?,?)",
            (contractor_id, now(), name, email, message),
        )


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def conn():
    c = sqlite3.connect(settings.db_path)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with conn() as c:
        c.executescript(SCHEMA)


def create_report(report_id, email, zip_code, trade, quote_text, file_name, file_mime, status):
    with conn() as c:
        c.execute(
            "INSERT INTO reports (id, created_at, email, zip_code, trade, status, quote_text, file_name, file_mime)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (report_id, now(), email, zip_code, trade, status, quote_text, file_name, file_mime),
        )


def get_report(report_id):
    with conn() as c:
        row = c.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        return dict(row) if row else None


def update_report(report_id, **fields):
    keys = ", ".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE reports SET {keys} WHERE id=?", (*fields.values(), report_id))


def set_report_result(report_id, report: dict):
    update_report(report_id, status="complete", report_json=json.dumps(report))


def set_report_failed(report_id, error: str):
    update_report(report_id, status="failed", error=error[:2000])


def add_followup(report_id: str, contractor_reply: str, response: dict):
    with conn() as c:
        c.execute(
            "INSERT INTO followups (report_id, created_at, contractor_reply, response_json) VALUES (?,?,?,?)",
            (report_id, now(), contractor_reply, json.dumps(response)),
        )


def add_waitlist(email: str):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO waitlist (email, created_at) VALUES (?,?)", (email, now()))
