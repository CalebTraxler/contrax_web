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
    report_json TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS waitlist (
    email TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
"""


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


def add_waitlist(email: str):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO waitlist (email, created_at) VALUES (?,?)", (email, now()))
