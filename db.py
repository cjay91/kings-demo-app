"""Mock e-Channelling database.

Schema mirrors the four API endpoints in the King's Hospital voice bot build
guide (Section 5.1) so this can later be swapped for real e-Channelling API
calls without changing the agent's tool interface.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from rapidfuzz import fuzz

DB_PATH = Path(__file__).parent / "hospital.db"

# Only used for name matching, deliberately NOT specialty matching -- see
# search_doctors_by_specialty for why. Confirmed via testing: legitimate
# partial/near-miss doctor names score 90-100 here, while the worst-case
# similarity between two DIFFERENT doctors' names tops out around 65, so
# there's a clean gap to threshold on.
NAME_FUZZY_THRESHOLD = 80

SCHEMA = """
CREATE TABLE IF NOT EXISTS doctors (
    doc_id INTEGER PRIMARY KEY,
    doc_name TEXT NOT NULL,
    doc_name_si TEXT NOT NULL,      -- Sinhala transliteration, e.g. "නිමල් පෙරේරා"
    specialty TEXT NOT NULL,
    specialty_si TEXT NOT NULL,     -- Sinhala term, e.g. "හෘද රෝග"
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


def init_db(reset: bool = False):
    with get_conn() as conn:
        if reset:
            # Drop-and-recreate rather than rely on IF NOT EXISTS: a table
            # created under an older schema version (e.g. before doc_name_si/
            # specialty_si existed) would otherwise silently keep its old
            # columns forever, breaking every seed() call after a schema
            # change. Order matters for the foreign keys (children first).
            conn.executescript(
                "DROP TABLE IF EXISTS running_status;"
                "DROP TABLE IF EXISTS sessions;"
                "DROP TABLE IF EXISTS doctors;"
            )
        conn.executescript(SCHEMA)


def search_doctors_by_name(name: str) -> tuple[list[dict], bool]:
    """Returns (matches, is_fuzzy). Tries an exact substring match first;
    if that finds nothing, falls back to fuzzy matching (rapidfuzz
    partial_ratio) against both the English and Sinhala names, so a
    mistranscribed or partial name (e.g. STT noise, or just a first name)
    still resolves. is_fuzzy tells the caller the match is approximate,
    so the agent can confirm it with the caller instead of stating it with
    full confidence -- see tools.py."""
    with get_conn() as conn:
        exact = conn.execute(
            "SELECT * FROM doctors WHERE doc_name LIKE ? OR doc_name_si LIKE ?",
            (f"%{name}%", f"%{name}%"),
        ).fetchall()
    if exact:
        return [dict(r) for r in exact], False

    with get_conn() as conn:
        all_doctors = [dict(r) for r in conn.execute("SELECT * FROM doctors").fetchall()]

    scored = [
        (max(fuzz.partial_ratio(name, d["doc_name"]), fuzz.partial_ratio(name, d["doc_name_si"])), d)
        for d in all_doctors
    ]
    scored = [(score, d) for score, d in scored if score >= NAME_FUZZY_THRESHOLD]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [d for _, d in scored], True


def search_doctors_by_specialty(specialty: str) -> list[dict]:
    """Exact substring match only -- deliberately NOT fuzzy, unlike
    search_doctors_by_name. Tested and rejected: most specialty terms
    share a common trailing word ("රෝග" / disease), so character-similarity
    fuzzy matching can't reliably tell a genuine near-miss from a
    completely different, wrong specialty -- both land in the same ~65-77
    similarity band. Confirmed with the actual STT error seen in testing
    ("විරුද්ධ රෝග" heard for "හෘද රෝග"), which fuzzy-matched other, wrong
    specialties just as confidently as the correct one. Safer to return
    nothing (see get_all_specialties for the fallback) than to silently
    guess wrong.

    Checks containment in BOTH directions, not just "DB value contains the
    query": a caller asking for "හෘද රෝග විශේෂඥ" (cardiology *specialist*)
    was falling through to "no match" and getting offered the full
    specialty list instead of just being understood, because the query is
    LONGER than the stored specialty ("හෘද රෝග" alone) -- the query
    contains the specialty, not the other way around. Still an exact
    substring check either way, so the fuzzy-matching risk above doesn't
    apply here."""
    with get_conn() as conn:
        all_doctors = [dict(r) for r in conn.execute("SELECT * FROM doctors").fetchall()]
    return [
        d
        for d in all_doctors
        if specialty in d["specialty"]
        or specialty in d["specialty_si"]
        or d["specialty"] in specialty
        or d["specialty_si"] in specialty
    ]


def get_all_specialties() -> list[dict]:
    """All distinct specialties, to offer a caller the full list when
    their specialty query didn't match anything exactly."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT specialty, specialty_si FROM doctors ORDER BY specialty"
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
            SELECT d.doc_id, d.doc_name, d.doc_name_si, d.specialty, d.specialty_si,
                   s.session_id, s.start_time, s.total_slots
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
