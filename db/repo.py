"""Thin read/write functions over the SQLite schema. No business logic."""

import json
import sqlite3
from collections import defaultdict

from domain.models import Course, PlanResult, StudentProfile

TERM_ORDER = {"fall": 0, "spring": 1}


def _grouped(conn: sqlite3.Connection, sql: str) -> dict[str, list[str]]:
    """Run a two-column query and group the second column by the first."""
    out: dict[str, list[str]] = defaultdict(list)
    for key, value in conn.execute(sql):
        out[key].append(value)
    return out


def load_catalog(conn: sqlite3.Connection) -> dict[str, Course]:
    """Build every Course from `courses` and its join tables, keyed and sorted by code."""
    prereqs = _grouped(conn, "SELECT course_code, prereq_code FROM course_prereqs"
                             " ORDER BY rowid")
    coreqs = _grouped(conn, "SELECT course_code, coreq_code FROM course_coreqs"
                            " ORDER BY rowid")
    slots = _grouped(conn, "SELECT course_code, slot FROM course_slots"
                           " ORDER BY rowid")
    offered = _grouped(conn, "SELECT course_code, term FROM course_offerings")
    catalog: dict[str, Course] = {}
    for row in conn.execute("SELECT * FROM courses ORDER BY code"):
        code = row["code"]
        catalog[code] = Course(
            code=code,
            title=row["title"],
            credits=row["credits"],
            prereqs=tuple(prereqs[code]),
            coreqs=tuple(coreqs[code]),
            offered=tuple(sorted(offered[code], key=TERM_ORDER.__getitem__)),
            slots=tuple(slots[code]),
            category=row["category"],
            track=row["track"],
        )
    return catalog


def load_profiles(conn: sqlite3.Connection) -> dict[str, StudentProfile]:
    """Load all profiles with their completed-course sets, keyed by name."""
    completed = _grouped(conn, "SELECT profile_name, course_code FROM profile_completed")
    return {
        row["name"]: StudentProfile(
            name=row["name"],
            completed=frozenset(completed[row["name"]]),
            target_track=row["target_track"],
            max_credits=row["max_credits"],
            start_term=row["start_term"],
            elective_credits_required=row["elective_credits_required"],
        )
        for row in conn.execute("SELECT * FROM profiles ORDER BY rowid")
    }


def load_profile(conn: sqlite3.Connection, name: str) -> StudentProfile:
    """Load one profile by name; raises KeyError if it does not exist."""
    profiles = load_profiles(conn)
    if name not in profiles:
        raise KeyError(f"unknown profile: {name}")
    return profiles[name]


def save_plan(conn: sqlite3.Connection, profile: StudentProfile, algorithm: str,
              max_credits: int, result: PlanResult) -> int:
    """Persist a plan and its rule log in one transaction; return the new plan id."""
    semesters = [[c.code for c in term] for term in result.semesters]
    plan_json = json.dumps({
        "semesters": semesters,
        "start_term": profile.start_term,
        "completed": sorted(profile.completed),
        "stats": result.stats,
    })
    with conn:
        cur = conn.execute(
            "INSERT INTO saved_plans (profile_name, target_track, algorithm, max_credits,"
            " total_terms, total_credits, expanded, elapsed_ms, cost, plan_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (profile.name, profile.target_track, algorithm, max_credits,
             len(result.semesters), sum(c.credits for t in result.semesters for c in t),
             int(result.stats.get("expanded", 0)), float(result.stats.get("ms", 0.0)),
             float(result.stats.get("cost", 0.0)), plan_json),
        )
        plan_id = int(cur.lastrowid)
        conn.executemany(
            "INSERT INTO rule_log (plan_id, seq, rule, subject, ok, detail)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(plan_id, i, r.rule, r.subject, int(r.ok), r.detail)
             for i, r in enumerate(result.log)],
        )
    return plan_id


def list_saved_plans(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return saved-plan summary rows, newest first."""
    return conn.execute(
        "SELECT id, profile_name, target_track, algorithm, max_credits, total_terms,"
        " total_credits, expanded, elapsed_ms, cost, created_at"
        " FROM saved_plans ORDER BY created_at DESC, id DESC"
    ).fetchall()


def load_saved_plan(conn: sqlite3.Connection, plan_id: int) -> dict:
    """Return {"meta": row-dict, "semesters": [[code]], "log": [row-dict]} for a plan."""
    row = conn.execute("SELECT * FROM saved_plans WHERE id = ?", (plan_id,)).fetchone()
    if row is None:
        raise KeyError(f"no saved plan with id {plan_id}")
    meta = dict(row)
    payload = json.loads(meta.pop("plan_json"))
    log = conn.execute(
        "SELECT seq, rule, subject, ok, detail FROM rule_log WHERE plan_id = ? ORDER BY seq",
        (plan_id,),
    ).fetchall()
    return {
        "meta": meta | payload,
        "semesters": payload["semesters"],
        "log": [dict(r) for r in log],
    }


def delete_saved_plan(conn: sqlite3.Connection, plan_id: int) -> None:
    """Delete a saved plan; its rule_log rows go with it via ON DELETE CASCADE."""
    with conn:
        conn.execute("DELETE FROM saved_plans WHERE id = ?", (plan_id,))
