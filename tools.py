"""Agent tools mapped 1:1 to the four e-Channelling API endpoints described in
the King's Hospital voice bot build guide (Section 5.1). Each tool currently
queries the local mock DB (db.py) instead of the real e-Channelling API — the
signatures and return shapes are kept close to the real endpoints so swapping
the implementation later is a small change, not a rewrite.
"""

from datetime import datetime, timedelta

from livekit.agents import RunContext, function_tool

import db


def _relative_date(text: str) -> str:
    """Resolve simple relative date words to YYYY-MM-DD. Falls back to today."""
    text = text.strip().lower()
    today = datetime.now()
    if text in ("today", "අද"):
        return today.strftime("%Y-%m-%d")
    if text in ("tomorrow", "හෙට"):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if text in ("day after tomorrow", "අනිද්දා"):
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")
    return text  # assume already YYYY-MM-DD


def _format_time_si(hhmm: str) -> str:
    """Format a 24-hour "HH:MM" string as 12-hour Sinhala time, e.g. "15:00"
    -> "සවස 3:00". Done here rather than left to the LLM since correctly
    converting 24-hour time into Sinhala උදෑසන/සවස wording on the fly is
    exactly the kind of small formatting detail an LLM can get inconsistent
    about -- pushing it into the tool output makes it always correct."""
    hour, minute = map(int, hhmm.split(":"))
    period = "උදෑසන" if hour < 12 else "සවස"
    hour12 = hour % 12 or 12
    return f"{period} {hour12}:{minute:02d}"


@function_tool()
async def search_consultants(context: RunContext, query: str) -> str:
    """Search for consultants (doctors) by name or by specialty.

    Use this when the caller mentions a doctor's name (e.g. "Dr. Perera") or a
    specialty (e.g. "cardiology", "orthopaedics"). Tries specialty first, then
    falls back to a name search.

    Args:
        query: The doctor's name, OR just the bare specialty/condition term
            -- e.g. "cardiology" or "හෘද රෝග", NOT "cardiology specialist" or
            "හෘද රෝග විශේෂඥ". Strip descriptor words like
            specialist/doctor/විශේෂඥ/වෛද්‍ය/ඩොක්ටර් before passing this in;
            they aren't part of the specialty name in the database and will
            cause a real match to be missed.
    """
    results = db.search_doctors_by_specialty(query)
    is_fuzzy = False
    if not results:
        results, is_fuzzy = db.search_doctors_by_name(query)

    if not results:
        specialties = db.get_all_specialties()
        available = ", ".join(f"{s['specialty_si']} ({s['specialty']})" for s in specialties)
        return f"No consultants found matching '{query}'. Available specialties: {available}."

    prefix = (
        "Found consultants (approximate name match -- confirm the name with "
        "the caller before proceeding):\n"
        if is_fuzzy
        else "Found consultants:\n"
    )
    lines = [
        f"{d['doc_name_si']} / {d['doc_name']} ({d['specialty_si']} / {d['specialty']}) "
        f"- {d['qualifications']}"
        for d in results
    ]
    return prefix + "\n".join(lines)


@function_tool()
async def get_doctor_sessions(
    context: RunContext, doctor_name: str, date: str | None = None
) -> str:
    """Look up upcoming clinic sessions for a specific doctor, optionally on a given date.

    Use this once the caller has named a specific doctor and you need their
    available session dates and times.

    Args:
        doctor_name: The doctor's name as mentioned by the caller.
        date: Optional date to filter by. Accepts "today", "tomorrow", or YYYY-MM-DD.
    """
    matches, is_fuzzy = db.search_doctors_by_name(doctor_name)
    if not matches:
        return f"No doctor found matching '{doctor_name}'."

    doc = matches[0]
    fuzzy_note = (
        " (approximate name match -- confirm with the caller that this is who they meant)"
        if is_fuzzy
        else ""
    )
    resolved_date = _relative_date(date) if date else None
    sessions = db.get_sessions_for_doctor(doc["doc_id"], resolved_date)

    if not sessions:
        scope = f" on {resolved_date}" if resolved_date else ""
        return f"{doc['doc_name_si']} / {doc['doc_name']}{fuzzy_note} has no available sessions{scope}."

    lines = [
        f"Session {s['session_id']}: {s['session_date']} at {_format_time_si(s['start_time'])} "
        f"({s['total_slots']} slots)"
        for s in sessions
    ]
    return (
        f"{doc['doc_name_si']} / {doc['doc_name']} ({doc['specialty_si']} / {doc['specialty']}){fuzzy_note} "
        "sessions:\n" + "\n".join(lines)
    )


@function_tool()
async def get_available_doctors_by_date(context: RunContext, date: str) -> str:
    """Find all doctors with an available session on a specific date.

    Use this when the caller asks something like "who is available tomorrow"
    without naming a specific doctor or specialty.

    Args:
        date: The date to check. Accepts "today", "tomorrow", or YYYY-MM-DD.
    """
    resolved_date = _relative_date(date)
    rows = db.get_available_doctors_by_date(resolved_date)

    if not rows:
        return f"No doctors have sessions on {resolved_date}."

    lines = [
        f"{r['doc_name_si']} / {r['doc_name']} ({r['specialty_si']} / {r['specialty']}) "
        f"at {_format_time_si(r['start_time'])} [session {r['session_id']}]"
        for r in rows
    ]
    return f"Doctors available on {resolved_date}:\n" + "\n".join(lines)


@function_tool()
async def get_running_number(context: RunContext, session_id: int) -> str:
    """Get the live running (queue) number for an ongoing clinic session.

    Use this when the caller asks how far along a doctor's queue is, e.g.
    "what's the running number for Dr. Perera's session".

    Args:
        session_id: The numeric session ID, from a prior search result.
    """
    status = db.get_running_status(session_id)
    if not status:
        return f"No live running-number data available for session {session_id}."

    return (
        f"Session {session_id}: currently serving number {status['current_number']}, "
        f"next number expected around {_format_time_si(status['expected_time'])}."
    )


HOSPITAL_TOOLS = [
    search_consultants,
    get_doctor_sessions,
    get_available_doctors_by_date,
    get_running_number,
]
