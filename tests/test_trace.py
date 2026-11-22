"""Tests for step-by-step search tracing."""

import pytest

from domain.catalog import CATALOG
from domain.profiles import PROFILES
from reasoning.search import run_plan
from reasoning.trace import node_title, statuses_at, trace_search

CAT = {c.code: c for c in CATALOG}
PROF = {p.name: p for p in PROFILES}
CASES = [(p.name, a, cap) for p in PROFILES for a in ("bfs", "ucs", "astar") for cap in (12, 18)]


@pytest.mark.parametrize("name,algorithm,cap", CASES)
def test_trace_matches_untraced_run(name, algorithm, cap):
    p = PROF[name]
    trace = trace_search(p, CAT, algorithm, cap)
    plain = run_plan(p, CAT, algorithm, cap)
    assert [[c.code for c in t] for t in trace.result.semesters] == \
        [[c.code for c in t] for t in plain.semesters]
    assert trace.result.stats["expanded"] == plain.stats["expanded"]
    assert sum(e.kind == "expand" for e in trace.events) == plain.stats["expanded"]


@pytest.mark.parametrize("name,algorithm,cap", CASES)
def test_trace_shape(name, algorithm, cap):
    trace = trace_search(PROF[name], CAT, algorithm, cap)
    assert trace.events[0].kind == "start" and trace.events[-1].kind == "goal"
    assert [e.step for e in trace.events] == list(range(len(trace.events)))
    assert not trace.truncated
    path_combos = [trace.nodes[n].combo for n in trace.path[1:]]
    assert path_combos == [tuple(c.code for c in t) for t in trace.result.semesters]
    assert trace.path[0] == 0 and trace.path[-1] == trace.goal_node


def test_every_node_has_a_known_parent():
    trace = trace_search(PROF["Transfer"], CAT, "bfs", 12)
    for node in trace.nodes.values():
        assert node.parent is None or node.parent in trace.nodes


def test_statuses_progress():
    trace = trace_search(PROF["On-track"], CAT, "astar", 18)
    assert statuses_at(trace, 0) == {0: "frontier"}
    assert statuses_at(trace, 1)[0] == "current"
    final = statuses_at(trace, len(trace.events) - 1)
    assert final[trace.goal_node] == "goal"
    assert all(final[n] == "path" for n in trace.path[:-1])


def test_astar_trace_is_shorter_than_ucs():
    for p in PROFILES:
        assert (len(trace_search(p, CAT, "astar", 12).events)
                < len(trace_search(p, CAT, "ucs", 12).events))


def test_node_titles():
    trace = trace_search(PROF["On-track"], CAT, "astar", 18)
    assert node_title(trace.nodes[0], "fall") == "Start"
    assert node_title(trace.nodes[trace.goal_node], "fall") == "Fall 2027 +AI401"


def test_trace_deterministic():
    a = trace_search(PROF["Heavy electives"], CAT, "ucs", 15)
    b = trace_search(PROF["Heavy electives"], CAT, "ucs", 15)
    assert [e.text for e in a.events] == [e.text for e in b.events]
