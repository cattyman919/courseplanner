"""CoursePath web server: a JSON API over the symbolic planner, plus the static front end.

Run with ``make run`` (``uv run uvicorn api.server:app``). The server is stateless: the
browser sends the student's committed terms with each request and the Python rule engine
answers. Nothing here calls the network.
"""

from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api import serialize
from db import repo
from db.connection import get_connection, init_db
from domain.models import Course, PlanResult, RuleResult, StudentProfile
from reasoning.advisor import (
    available_now,
    check_term,
    course_verdict,
    progress,
    state_after,
    suggest_rest,
)
from reasoning.rules import required_courses_for, term_label
from reasoning.search import ALGORITHMS, run_plan
from reasoning.trace import trace_search

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
Algorithm = Literal["bfs", "ucs", "astar"]
Track = Literal["ai", "systems", "theory"]
Credits = Field(ge=12, le=21)


class PlanRequest(BaseModel):
    profile: str
    track: Track | None = None
    max_credits: int = Credits
    algorithm: Algorithm = "astar"
    compare: bool = False


class Student(BaseModel):
    completed: list[str] = []
    target_track: Track = "ai"
    start_term: Literal["fall", "spring"] = "fall"
    elective_credits_required: int = Field(default=9, ge=0, le=30)
    max_credits: int = Credits


class BuilderRequest(BaseModel):
    student: Student
    terms: list[list[str]] = []
    picks: list[str] = []
    algorithm: Algorithm = "astar"


def create_app(db_path: Path | None = None) -> FastAPI:
    """Build the app against a SQLite file (the project DB by default)."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        catalog: dict[str, Course] = repo.load_catalog(conn)
        profiles: dict[str, StudentProfile] = repo.load_profiles(conn)
    finally:
        conn.close()

    app = FastAPI(title="CoursePath", docs_url="/api/docs", openapi_url="/api/openapi.json")

    def db():
        return get_connection(db_path)

    def preset(req: PlanRequest) -> StudentProfile:
        if req.profile not in profiles:
            raise HTTPException(422, f"unknown profile: {req.profile}")
        base = profiles[req.profile]
        return replace(base, target_track=req.track or base.target_track)

    def known(codes: list[str]) -> list[str]:
        bad = sorted(set(codes) - set(catalog))
        if bad:
            raise HTTPException(422, f"unknown course(s): {', '.join(bad)}")
        return codes

    @lru_cache(maxsize=256)
    def cached_plan(name: str, track: str, max_credits: int, algorithm: str) -> PlanResult:
        return run_plan(replace(profiles[name], target_track=track), catalog, algorithm,
                        max_credits)

    @lru_cache(maxsize=64)
    def cached_trace(name: str, track: str, max_credits: int, algorithm: str) -> dict:
        student = replace(profiles[name], target_track=track)
        return serialize.trace(trace_search(student, catalog, algorithm, max_credits))

    # --- reference data -------------------------------------------------------------

    @app.get("/api/catalog")
    def get_catalog() -> list[dict]:
        return [serialize.course(c) for c in catalog.values()]

    @app.get("/api/profiles")
    def get_profiles() -> list[dict]:
        return [serialize.profile(p) for p in profiles.values()]

    # --- AI planner -----------------------------------------------------------------

    @app.post("/api/plan")
    def plan(req: PlanRequest) -> dict:
        student = preset(req)
        args = (req.profile, student.target_track, req.max_credits)
        out = serialize.plan(cached_plan(*args, req.algorithm), student.start_term)
        out["profile"] = serialize.profile(student)
        out["required"] = sorted(required_courses_for(student, catalog))
        if req.compare:
            out["comparison"] = {a: serialize.plan(cached_plan(*args, a), student.start_term)
                                 for a in ALGORITHMS}
        return out

    @app.post("/api/trace")
    def trace(req: PlanRequest) -> dict:
        student = preset(req)
        args = (req.profile, student.target_track, req.max_credits)
        out = cached_trace(*args, req.algorithm)
        expanded = {a: cached_plan(*args, a).stats["expanded"] for a in ALGORITHMS}
        return out | {"expanded_by_algorithm": expanded}

    # --- Build my plan --------------------------------------------------------------

    def builder_student(req: BuilderRequest) -> StudentProfile:
        s = req.student
        known(s.completed)
        for term in req.terms:
            known(term)
        known(req.picks)
        return StudentProfile("You", frozenset(s.completed), s.target_track, s.max_credits,
                              s.start_term, s.elective_credits_required)

    @app.post("/api/builder/check")
    def builder_check(req: BuilderRequest) -> dict:
        student = builder_student(req)
        state = state_after(student, req.terms)
        required = required_courses_for(student, catalog)
        courses = []
        for code, c in catalog.items():
            if code in state.completed:
                continue
            group = ("required" if code in required
                     else "elective" if c.category == "elective" else "other")
            verdict = serialize.rule(course_verdict(c, state, student, catalog))
            courses.append(serialize.course(c) | {"group": group, "verdict": verdict})
        check = check_term(req.picks, state, student, catalog, student.max_credits)
        return {
            "term_index": state.term_index,
            "term_label": term_label(student.start_term, state.term_index),
            "term_labels": [term_label(student.start_term, i) for i in range(len(req.terms))],
            "courses": courses,
            "check": serialize.term_check(check),
            "available": [c.code for c in available_now(state, student, catalog)],
            "progress": serialize.progress(progress(state, student, catalog)),
            "required": sorted(required),
        }

    @app.post("/api/builder/suggest")
    def builder_suggest(req: BuilderRequest) -> dict:
        student = builder_student(req)
        state = state_after(student, req.terms)
        result = suggest_rest(state, student, catalog, student.max_credits, req.algorithm)
        return serialize.plan(result, student.start_term, offset=state.term_index)

    # --- saved plans (SQLite) -------------------------------------------------------

    @app.get("/api/plans")
    def list_plans() -> list[dict]:
        conn = db()
        try:
            return [dict(r) for r in repo.list_saved_plans(conn)]
        finally:
            conn.close()

    @app.post("/api/plans", status_code=201)
    def save(req: PlanRequest) -> dict:
        student = preset(req)
        result = cached_plan(req.profile, student.target_track, req.max_credits,
                             req.algorithm)
        conn = db()
        try:
            return {"id": repo.save_plan(conn, student, req.algorithm, req.max_credits,
                                         result)}
        finally:
            conn.close()

    @app.get("/api/plans/{plan_id}")
    def load(plan_id: int) -> dict:
        conn = db()
        try:
            saved = repo.load_saved_plan(conn, plan_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        finally:
            conn.close()
        meta = saved["meta"]
        result = PlanResult(
            semesters=[[catalog[c] for c in t if c in catalog] for t in saved["semesters"]],
            log=[RuleResult(r["subject"], bool(r["ok"]), r["rule"], r["detail"] or "")
                 for r in saved["log"]],
            stats=meta.get("stats") or {"expanded": meta["expanded"], "generated": 0,
                                        "ms": meta["elapsed_ms"], "cost": meta["cost"]},
            algorithm=meta["algorithm"])
        return {"meta": {k: v for k, v in meta.items() if k != "stats"},
                "plan": serialize.plan(result, meta.get("start_term", "fall"))}

    @app.delete("/api/plans/{plan_id}", status_code=204)
    def delete(plan_id: int) -> None:
        conn = db()
        try:
            repo.delete_saved_plan(conn, plan_id)
        finally:
            conn.close()

    # --- static front end -----------------------------------------------------------

    if WEB_DIR.is_dir():
        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

        app.mount("/", StaticFiles(directory=WEB_DIR), name="web")

    return app


app = create_app()
