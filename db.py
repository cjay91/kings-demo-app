"""Mock e-Channelling database.

Schema mirrors the four API endpoints in the King's Hospital voice bot build
guide (Section 5.1) so this can later be swapped for real e-Channelling API
calls without changing the agent's tool interface.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "hospital.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS doctors (
    doc_id INTEGER PRIMARY KEY,
    doc_name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    qualifications TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES doctors(doc_id),
    session_date TEXT NOT NULL,      -- YYYY-MM-DD
    start_time TEXT NOT NULL,        -- HH:MM
    hospital_code TEXT NOT NULL DEFAULT 'KH-COL',
    total_slots INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS running_status (
    session_id INTEGER PRIMARY KEY REFERENCES sessions(session_id),
    current_number INTEGER NOT NULL,
    expected_time TEXT NOT NULL,      -- HH:MM, estimated time for next number
    updated_at TEXT NOT NULL
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def search_doctors_by_name(name: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM doctors WHERE doc_name LIKE ?",
            (f"%{name}%",),
        ).fetchall()
        return [dict(r) for r in rows]


def search_doctors_by_specialty(specialty: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM doctors WHERE specialty LIKE ?",
            (f"%{specialty}%",),
        ).fetchall()
        return [dict(r) for r in rows]


def get_sessions_for_doctor(doc_id: int, date: str | None = None):
    with get_conn() as conn:
        if date:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE doc_id = ? AND session_date = ? ORDER BY start_time",
                (doc_id, date),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE doc_id = ? AND session_date >= date('now') "
                "ORDER BY session_date, start_time",
                (doc_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_available_doctors_by_date(date: str):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.doc_id, d.doc_name, d.specialty, s.session_id, s.start_time, s.total_slots
            FROM sessions s
            JOIN doctors d ON d.doc_id = s.doc_id
            WHERE s.session_date = ?
            ORDER BY d.specialty, s.start_time
            """,
            (date,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_running_status(session_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM running_status WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None


if __name__ == "__main__":
    init_db()
    print(f"Initialized schema at {DB_PATH}")
