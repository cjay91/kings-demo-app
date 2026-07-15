"""Seed the mock hospital.db with sample doctors, sessions, and running status.

Run directly: python seed.py
Safe to re-run — wipes and re-creates the three tables each time.
"""

from datetime import datetime, timedelta

import db

DOCTORS = [
    ("Dr. Nimal Perera", "Cardiology", "MBBS, MD (Cardiology), FRCP"),
    ("Dr. Priyanka Fernando", "Cardiology", "MBBS, MD (Cardiology)"),
    ("Dr. Ashan Silva", "Orthopaedics", "MBBS, MS (Orthopaedic Surgery)"),
    ("Dr. Chamari Wickramasinghe", "Orthopaedics", "MBBS, MS (Ortho), FRCS"),
    ("Dr. Ruwan Jayasuriya", "Pediatrics", "MBBS, DCH, MD (Paediatrics)"),
    ("Dr. Dilani Gunawardena", "Pediatrics", "MBBS, MD (Paediatrics)"),
    ("Dr. Kasun Rathnayake", "Dermatology", "MBBS, MD (Dermatology)"),
    ("Dr. Sanduni Bandara", "ENT", "MBBS, MS (ENT)"),
    ("Dr. Mahesh Karunaratne", "General Medicine", "MBBS, MD (Medicine)"),
    ("Dr. Tharushi Amarasinghe", "Gynaecology", "MBBS, MS (OBGYN)"),
]

# (doc index, day offset from today, start_time, total_slots)
SESSIONS = [
    (0, 1, "09:00", 20),
    (0, 3, "09:00", 20),
    (1, 2, "14:00", 15),
    (2, 1, "10:00", 12),
    (2, 4, "10:00", 12),
    (3, 2, "16:00", 10),
    (4, 1, "08:30", 25),
    (4, 2, "08:30", 25),
    (5, 3, "13:00", 20),
    (6, 1, "11:00", 15),
    (7, 2, "09:30", 12),
    (8, 1, "15:00", 18),
    (8, 5, "15:00", 18),
    (9, 3, "10:30", 14),
]


def run():
    db.init_db()
    with db.get_conn() as conn:
        conn.execute("DELETE FROM running_status")
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM doctors")

        for i, (name, specialty, quals) in enumerate(DOCTORS):
            conn.execute(
                "INSERT INTO doctors (doc_id, doc_name, specialty, qualifications) VALUES (?, ?, ?, ?)",
                (i + 1, name, specialty, quals),
            )

        today = datetime.now()
        session_id = 1
        for doc_idx, day_offset, start_time, total_slots in SESSIONS:
            session_date = (today + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO sessions (session_id, doc_id, session_date, start_time, hospital_code, total_slots) "
                "VALUES (?, ?, ?, ?, 'KH-COL', ?)",
                (session_id, doc_idx + 1, session_date, start_time, total_slots),
            )
            # Give the first few sessions a live running number, as if in progress.
            if day_offset == 1:
                conn.execute(
                    "INSERT INTO running_status (session_id, current_number, expected_time, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (session_id, 7, "10:15", today.strftime("%Y-%m-%d %H:%M")),
                )
            session_id += 1

    print(f"Seeded {len(DOCTORS)} doctors and {len(SESSIONS)} sessions into {db.DB_PATH}")


if __name__ == "__main__":
    run()
