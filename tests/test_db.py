"""Tests for the SQLite schema, seed, and repository layer."""

from pathlib import Path

import pytest

from db import repo
from db.connection import get_connection, init_db
from domain.catalog import CATALOG
from domain.models import Course, PlanResult, RuleResult
from domain.profiles import PROFILES

TABLES = {
    "courses", "course_prereqs", "course_coreqs", "course_slots", "course_offerings",
    "profiles", "profile_completed", "saved_plans", "rule_log",
}


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture
def conn(db_path: Path):
    c = get_connection(db_path)
    yield c
    c.close()


def _sample_result(catalog: dict[str, Course]) -> PlanResult:
    return PlanResult(
        semesters=[[catalog["CS301"], catalog["MATH301"]], [catalog["AI320"]]],
        log=[
            RuleResult("CS301", True, "OK", "eligible"),
            RuleResult("GE102", False, "PRUNED", "not needed for track ai"),
            RuleResult("AI401", False, "PREREQ", "missing prerequisite(s): AI320"),
        ],
        stats={"expanded": 5, "generated": 12, "ms": 1.5, "cost": 2.5},
        algorithm="astar",
    )


def test_init_creates_tables_and_seeds(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert TABLES <= names
    assert conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == len(CATALOG)
    assert conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == len(PROFILES)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


def test_init_is_idempotent(db_path, conn):
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    init_db(db_path)
    init_db(db_path)
    again = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    assert counts == again


def test_schema_version_mismatch_raises(db_path):
    c = get_connection(db_path)
    c.execute("PRAGMA user_version = 99")
    c.close()
    with pytest.raises(RuntimeError, match="Delete"):
        init_db(db_path)


def test_load_catalog_round_trips_courses(conn):
    catalog = repo.load_catalog(conn)
    assert list(catalog) == sorted(catalog)
    assert catalog == {c.code: c for c in CATALOG}
    cs301 = catalog["CS301"]
    assert cs301.prereqs == ("CS201", "MATH210")
    assert cs301.offered == ("fall",)
    assert catalog["CS101"].slots == ("MW 13:00-14:30", "F 10:00-11:00")


def test_load_profiles_round_trip(conn):
    assert repo.load_profiles(conn) == {p.name: p for p in PROFILES}
    assert repo.load_profile(conn, "Transfer").start_term == "spring"
    with pytest.raises(KeyError):
        repo.load_profile(conn, "nobody")


def test_save_then_load_plan(conn):
    catalog = repo.load_catalog(conn)
    profile = repo.load_profile(conn, "On-track")
    result = _sample_result(catalog)
    plan_id = repo.save_plan(conn, profile, "astar", 18, result)
    loaded = repo.load_saved_plan(conn, plan_id)
    assert loaded["semesters"] == [["CS301", "MATH301"], ["AI320"]]
    assert len(loaded["log"]) == len(result.log)
    assert loaded["meta"]["total_credits"] == 10
    assert [r["id"] for r in repo.list_saved_plans(conn)] == [plan_id]


def test_delete_cascades_rule_log(conn):
    catalog = repo.load_catalog(conn)
    profile = repo.load_profile(conn, "On-track")
    plan_id = repo.save_plan(conn, profile, "astar", 18, _sample_result(catalog))
    repo.delete_saved_plan(conn, plan_id)
    assert conn.execute("SELECT COUNT(*) FROM saved_plans").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM rule_log").fetchone()[0] == 0
