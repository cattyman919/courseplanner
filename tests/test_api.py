"""Tests for the JSON API: it must return exactly what the Python engine computes."""

import pytest
from fastapi.testclient import TestClient

from api.server import create_app
from domain.catalog import CATALOG
from domain.profiles import PROFILES
from reasoning.search import run_plan

CAT = {c.code: c for c in CATALOG}
PROF = {p.name: p for p in PROFILES}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    return TestClient(create_app(tmp_path_factory.mktemp("db") / "test.db"))


def plan(client, **kw):
    body = {"profile": "On-track", "max_credits": 18, "algorithm": "astar"} | kw
    return client.post("/api/plan", json=body)


def test_catalog_and_profiles_come_from_sqlite(client):
    codes = [c["code"] for c in client.get("/api/catalog").json()]
    assert sorted(codes) == sorted(CAT)
    names = [p["name"] for p in client.get("/api/profiles").json()]
    assert names == [p.name for p in PROFILES]


def test_plan_matches_engine(client):
    out = plan(client).json()
    direct = run_plan(PROF["On-track"], CAT, "astar", 18)
    assert [t["courses"] for t in out["terms"]] == [[c.code for c in t]
                                                     for t in direct.semesters]
    assert (len(out["terms"]), out["total_credits"], out["stats"]["cost"]) == (3, 29, 4.45)
    assert out["terms"][0]["label"] == "Fall 2026"
    assert any(r["rule"] == "PRUNED" for r in out["log"])


def test_compare_reports_expanded_counts(client):
    out = plan(client, compare=True).json()
    expanded = {a: p["stats"]["expanded"] for a, p in out["comparison"].items()}
    assert expanded == {"bfs": 14, "ucs": 15, "astar": 4}


def test_transfer_plan_flags_inserted_prereqs(client):
    out = plan(client, profile="Transfer").json()
    assert len(out["terms"]) == 4
    assert {"CS201", "CS210", "MATH210"} <= set(out["inserted"])
    assert out["terms"][0]["label"].startswith("Spring")


def test_trace_replay_data(client):
    body = {"profile": "On-track", "max_credits": 12, "algorithm": "astar"}
    out = client.post("/api/trace", json=body).json()
    assert out["expanded_by_algorithm"] == {"bfs": 58, "ucs": 69, "astar": 26}
    assert out["events"][0]["kind"] == "start" and out["events"][-1]["kind"] == "goal"
    assert sum(e["kind"] == "expand" for e in out["events"]) == 26
    ids = {n["id"] for n in out["nodes"]}
    assert set(out["path"]) <= ids and out["path"][0] == 0
    assert all(e["status"] for e in out["events"] if e["node"] is not None)


def student(**kw):
    return {"completed": [], "target_track": "ai", "start_term": "fall",
            "elective_credits_required": 9, "max_credits": 18} | kw


def check(client, picks, terms=(), **kw):
    body = {"student": student(**kw), "terms": [list(t) for t in terms], "picks": picks}
    return client.post("/api/builder/check", json=body).json()


def test_builder_blocks_missing_prereq_and_warns_on_irrelevant(client):
    done = sorted(PROF["On-track"].completed)
    out = check(client, ["AI320", "SYS330"], completed=done)
    per = out["check"]["per_course"]
    assert per["AI320"]["rule"] == "PREREQ" and "CS301" in per["AI320"]["missing"]
    assert per["SYS330"]["rule"] == "PRUNED"
    assert not out["check"]["can_commit"]
    verdicts = {c["code"]: c["verdict"]["rule"] for c in out["courses"]}
    assert verdicts["CS301"] == "OK"


def test_builder_detects_conflict(client):
    p = PROF["Transfer"]
    out = check(client, ["CS210", "MATH210"], completed=sorted(p.completed),
                start_term=p.start_term)
    assert [r["rule"] for r in out["check"]["schedule"]] == ["CONFLICT"]
    assert not out["check"]["can_commit"]


def test_builder_commit_flow_and_suggest(client):
    first = check(client, ["CS101", "MATH101"])
    assert first["check"]["can_commit"] and first["term_label"] == "Fall 2026"
    after = check(client, [], terms=[["CS101", "MATH101"]])
    assert after["term_label"] == "Spring 2027"
    assert "CS101" not in {c["code"] for c in after["courses"]}
    body = {"student": student(), "terms": [["CS101", "MATH101"]], "algorithm": "astar"}
    rest = client.post("/api/builder/suggest", json=body).json()
    assert rest["terms"] and rest["terms"][0]["label"] == "Spring 2027"


def test_saved_plan_round_trip(client):
    body = {"profile": "On-track", "max_credits": 18, "algorithm": "astar"}
    plan_id = client.post("/api/plans", json=body).json()["id"]
    assert plan_id in [p["id"] for p in client.get("/api/plans").json()]
    loaded = client.get(f"/api/plans/{plan_id}").json()
    assert loaded["plan"]["terms"] == plan(client).json()["terms"]
    assert client.delete(f"/api/plans/{plan_id}").status_code == 204
    assert client.get(f"/api/plans/{plan_id}").status_code == 404


@pytest.mark.parametrize("body", [
    {"profile": "Nobody", "max_credits": 18},
    {"profile": "On-track", "max_credits": 30},
    {"profile": "On-track", "max_credits": 18, "algorithm": "dfs"},
])
def test_bad_plan_requests_are_rejected(client, body):
    assert client.post("/api/plan", json=body).status_code == 422


def test_unknown_course_is_rejected(client):
    body = {"student": student(completed=["XX999"]), "picks": []}
    assert client.post("/api/builder/check", json=body).status_code == 422
