"""Seed the mock hospital.db with sample doctors, sessions, and running status.

Run directly: python seed.py
Safe to re-run — wipes and re-creates the three tables each time.
"""

from datetime import datetime, timedelta

import db

# (English name, Sinhala name, English specialty, Sinhala specialty, qualifications)
# Sinhala names/specialties matter for matching: a Sinhala-speaking caller says
# names and specialties in Sinhala script, which won't LIKE-match English text
# in db.search_doctors_by_name/by_specialty without these columns.
DOCTORS = [
    ("Dr. Nimal Perera", "නිමල් පෙරේරා", "Cardiology", "හෘද රෝග", "MBBS, MD (Cardiology), FRCP"),
    ("Dr. Priyanka Fernando", "ප්‍රියංකා ප්‍රනාන්දු", "Cardiology", "හෘද රෝග", "MBBS, MD (Cardiology)"),
    ("Dr. Ashan Silva", "අශාන් සිල්වා", "Orthopaedics", "අස්ථි රෝග", "MBBS, MS (Orthopaedic Surgery)"),
    ("Dr. Chamari Wickramasinghe", "චමාරි වික්‍රමසිංහ", "Orthopaedics", "අස්ථි රෝග", "MBBS, MS (Ortho), FRCS"),
    ("Dr. Ruwan Jayasuriya", "රුවන් ජයසූරිය", "Pediatrics", "ළමා රෝග", "MBBS, DCH, MD (Paediatrics)"),
    ("Dr. Dilani Gunawardena", "දිලානි ගුණවර්ධන", "Pediatrics", "ළමා රෝග", "MBBS, MD (Paediatrics)"),
    ("Dr. Kasun Rathnayake", "කසුන් රත්නායක", "Dermatology", "සම් රෝග", "MBBS, MD (Dermatology)"),
    ("Dr. Sanduni Bandara", "සඳුනි බණ්ඩාර", "ENT", "කන් නාසය උගුර රෝග", "MBBS, MS (ENT)"),
    ("Dr. Mahesh Karunaratne", "මහේෂ් කරුණාරත්න", "General Medicine", "සාමාන්‍ය වෛද්‍ය", "MBBS, MD (Medicine)"),
    ("Dr. Tharushi Amarasinghe", "තරුෂි අමරසිංහ", "Gynaecology", "ස්ත්‍රී රෝග", "MBBS, MS (OBGYN)"),
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
    db.init_db(reset=True)
    with db.get_conn() as conn:
        for i, (name, name_si, specialty, specialty_si, quals) in enumerate(DOCTORS):
            conn.execute(
                "INSERT INTO doctors (doc_id, doc_name, doc_name_si, specialty, specialty_si, qualifications) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (i + 1, name, name_si, specialty, specialty_si, quals),
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
