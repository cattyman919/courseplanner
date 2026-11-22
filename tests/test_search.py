"""Tests for the state-space planners."""

import time
from dataclasses import replace

import pytest

from domain.catalog import CATALOG
from domain.models import PlanState, StudentProfile
from domain.profiles import PROFILES
from reasoning.rules import check_eligibility, check_schedule, goal_reached, term_label
from reasoning.search import (
    MAX_TERMS,
    edge_cost,
    heuristic,
    longest_prereq_chain,
    run_plan,
    state_key,
)

CAT = {c.code: c for c in CATALOG}
PROF = {p.name: p for p in PROFILES}
ALGOS = ("bfs", "ucs", "astar")
CAPS = (12, 15, 18)
SCENARIOS = [(p.name, a) for p in PROFILES for a in ALGOS]


@pytest.mark.parametrize("name,algorithm", SCENARIOS)
def test_every_scenario_yields_a_goal_plan(name, algorithm):
    p = PROF[name]
    result = run_plan(p, CAT, algorithm, 18)
    assert result.semesters and result.algorithm == algorithm
    done = p.completed | {c.code for term in result.semesters for c in term}
    assert goal_reached(PlanState(frozenset(done), len(result.semesters)), p, CAT)
    assert result.stats["expanded"] > 0 and result.stats["generated"] > 0
    assert result.stats["cost"] > 0


@pytest.mark.parametrize("name,algorithm", SCENARIOS)
@pytest.mark.parametrize("cap", [12, 18])
def test_every_planned_course_is_eligible_when_taken(name, algorithm, cap):
    p = PROF[name]
    state = PlanState(p.completed, 0)
    for term in run_plan(p, CAT, algorithm, cap).semesters:
        for course in term:
            assert check_eligibility(course, state, p.start_term).ok, course.code
        assert check_schedule(tuple(term), cap) == []
        state = PlanState(state.completed | {c.code for c in term}, state.term_index + 1)


@pytest.mark.parametrize("name", PROF)
def test_bfs_never_longer_than_ucs(name):
    bfs = run_plan(PROF[name], CAT, "bfs", 18)
    ucs = run_plan(PROF[name], CAT, "ucs", 18)
    assert len(bfs.semesters) <= len(ucs.semesters)
    assert bfs.stats["cost"] == len(bfs.semesters)


@pytest.mark.parametrize("name,algorithm", SCENARIOS)
def test_runtime_under_two_seconds(name, algorithm):
    t0 = time.perf_counter()
    run_plan(PROF[name], CAT, algorithm, 12)
    assert time.perf_counter() - t0 < 2.0


def test_deterministic():
    a = run_plan(PROF["On-track"], CAT, "ucs", 15)
    b = run_plan(PROF["On-track"], CAT, "ucs", 15)
    assert [[c.code for c in t] for t in a.semesters] == [[c.code for c in t] for t in b.semesters]
    assert a.log == b.log


def test_transfer_log_shows_prereq_and_conflict():
    log = run_plan(PROF["Transfer"], CAT, "ucs", 18).log
    rules = {r.rule for r in log}
    assert {"PREREQ", "CONFLICT", "OFFERING", "PRUNED"} <= rules
    assert any(r.rule == "PREREQ" and r.subject == "CS301" and "CS201" in r.detail for r in log)
    assert any(r.rule == "CONFLICT" and r.subject == "CS210/MATH210" for r in log)


def test_state_key_uses_term_name():
    s = PlanState(frozenset({"CS101"}), 1)
    assert state_key(s, "fall") == (frozenset({"CS101"}), "spring")
    assert state_key(s, "spring") == (frozenset({"CS101"}), "fall")


def test_term_labels():
    assert [term_label("fall", i) for i in range(3)] == ["Fall 2026", "Spring 2027", "Fall 2027"]
    assert term_label("spring", 0) == "Spring 2027"


def test_infeasible_when_course_never_offered():
    impossible = dict(CAT)
    impossible["AI401"] = replace(CAT["AI401"], offered=())
    result = run_plan(PROF["On-track"], impossible, "bfs", 18)
    assert result.semesters == []
    assert result.log[-1].rule == "INFEASIBLE" and str(MAX_TERMS) in result.log[-1].detail


def test_empty_catalog_does_not_crash():
    p = StudentProfile("Empty", frozenset(), "ai", elective_credits_required=0)
    result = run_plan(p, {}, "ucs", 18)
    assert result.semesters == [] and result.stats["expanded"] == 0


def test_unknown_algorithm_rejected():
    with pytest.raises(ValueError):
        run_plan(PROF["On-track"], CAT, "dfs", 18)


@pytest.mark.parametrize("name", PROF)
@pytest.mark.parametrize("cap", CAPS)
def test_astar_cost_equals_ucs_cost(name, cap):
    ucs = run_plan(PROF[name], CAT, "ucs", cap)
    astar = run_plan(PROF[name], CAT, "astar", cap)
    assert astar.stats["cost"] == pytest.approx(ucs.stats["cost"])
    assert astar.stats["expanded"] <= ucs.stats["expanded"]


@pytest.mark.parametrize("name", PROF)
def test_astar_expands_fewer_than_bfs_and_ucs(name):
    stats = {a: run_plan(PROF[name], CAT, a, 18).stats["expanded"] for a in ALGOS}
    assert stats["astar"] < stats["ucs"] and stats["astar"] < stats["bfs"]


@pytest.mark.parametrize("name", PROF)
@pytest.mark.parametrize("cap", CAPS)
def test_bfs_never_longer_than_astar(name, cap):
    bfs = run_plan(PROF[name], CAT, "bfs", cap)
    astar = run_plan(PROF[name], CAT, "astar", cap)
    assert len(bfs.semesters) <= len(astar.semesters)


@pytest.mark.parametrize("name", PROF)
@pytest.mark.parametrize("cap", CAPS)
def test_heuristic_admissible_and_consistent_along_plan(name, cap):
    p = PROF[name]
    plan = run_plan(p, CAT, "ucs", cap).semesters
    states = [PlanState(p.completed, 0)]
    for term in plan:
        last = states[-1]
        states.append(PlanState(last.completed | {c.code for c in term}, last.term_index + 1))
    costs = [edge_cost("ucs", tuple(t)) for t in plan]
    for i, s in enumerate(states):
        h = heuristic(s, p, CAT, cap)
        assert h <= sum(costs[i:]) + 1e-9, f"overestimates at term {i}"
        if i < len(plan):
            assert h <= costs[i] + heuristic(states[i + 1], p, CAT, cap) + 1e-9
    assert heuristic(states[-1], p, CAT, cap) == 0


def test_longest_prereq_chain():
    remaining = frozenset({"AI401", "CS301", "AI320"})
    assert longest_prereq_chain(remaining, frozenset({"CS101", "MATH101"}), CAT) == 4
    assert longest_prereq_chain(remaining, frozenset({"CS101", "CS201", "MATH210"}), CAT) == 3
    assert longest_prereq_chain(frozenset(), frozenset(), CAT) == 0
