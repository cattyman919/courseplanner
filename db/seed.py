"""Write the domain seed data (catalog and profiles) into SQLite."""

import sqlite3

from domain.catalog import CATALOG
from domain.profiles import PROFILES


def seed_if_empty(conn: sqlite3.Connection) -> bool:
    """Insert catalog and profiles in one transaction if `courses` is empty.

    Returns True if seeding happened, False if the DB was already populated.
    """
    if conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0] > 0:
        return False
    with conn:
        conn.executemany(
            "INSERT INTO courses (code, title, credits, category, track) VALUES (?, ?, ?, ?, ?)",
            [(c.code, c.title, c.credits, c.category, c.track) for c in CATALOG],
        )
        conn.executemany(
            "INSERT INTO course_prereqs (course_code, prereq_code) VALUES (?, ?)",
            [(c.code, p) for c in CATALOG for p in c.prereqs],
        )
        conn.executemany(
            "INSERT INTO course_coreqs (course_code, coreq_code) VALUES (?, ?)",
            [(c.code, q) for c in CATALOG for q in c.coreqs],
        )
        conn.executemany(
            "INSERT INTO course_slots (course_code, slot) VALUES (?, ?)",
            [(c.code, s) for c in CATALOG for s in c.slots],
        )
        conn.executemany(
            "INSERT INTO course_offerings (course_code, term) VALUES (?, ?)",
            [(c.code, t) for c in CATALOG for t in c.offered],
        )
        conn.executemany(
            "INSERT INTO profiles (name, target_track, max_credits, start_term,"
            " elective_credits_required) VALUES (?, ?, ?, ?, ?)",
            [(p.name, p.target_track, p.max_credits, p.start_term,
              p.elective_credits_required) for p in PROFILES],
        )
        conn.executemany(
            "INSERT INTO profile_completed (profile_name, course_code) VALUES (?, ?)",
            [(p.name, code) for p in PROFILES for code in sorted(p.completed)],
        )
    return True
