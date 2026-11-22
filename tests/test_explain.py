"""Tests for rule-log building and summarisation."""

import pytest

from domain.catalog import CATALOG
from domain.models import PlanResult, RuleResult
from domain.profiles import PROFILES
from reasoning.explain import (
    combo_label,
    course_level,
    inserted_prereqs,
    missing_prereqs,
    summarize,
    top_pruned,
)
from reasoning.search import run_plan

CAT = {c.code: c for c in CATALOG}
PROF = {p.name: p for p in PROFILES}


@pytest.fixture(scope="module")
def transfer() -> PlanResult:
    return run_plan(PROF["Transfer"], CAT, "astar", 18)


def test_combo_label():
    combo = (CAT["CS301"], CAT["CS310"], CAT["MATH301"])
    assert combo_label("fall", 0, combo) == "Fall 2026: CS301, CS310, MATH301"
    assert combo_label("fall", 1, ()) == "Spring 2027: (no eligible courses; wait)"


def test_log_has_one_label_row_per_term(transfer):
    labels = [r for r in transfer.log if r.rule == "OK" and r.subject[0].isupper()
              and " 20" in r.subject]
    assert len(labels) == len(transfer.semesters)
    assert labels[0].detail.startswith("Spring 2027: CS201")


def test_log_is_chronological(transfer):
    terms = [r.detail.split(":")[0] for r in transfer.log if r.rule in ("PREREQ", "OK")]
    order = ["Spring 2027", "Fall 2027", "Spring 2028", "Fall 2028"]
    assert [order.index(t) for t in terms] == sorted(order.index(t) for t in terms)


def test_prunes_logged_once_per_course(transfer):
    pruned = [r.subject for r in transfer.log if r.rule == "PRUNED"]
    assert len(pruned) == len(set(pruned))


def test_missing_prereqs_parsed():
    log = [
        RuleResult("CS301", False, "PREREQ", "Fall 2026: missing prerequisite(s): CS201, MATH210"),
        RuleResult("CS210", False, "OFFERING", "not offered in fall"),
    ]
    assert missing_prereqs(log) == {"CS201", "MATH210"}


def test_inserted_prereqs_flags_only_catch_up_courses(transfer):
    assert inserted_prereqs(transfer) == {"CS201", "CS210", "MATH210"}
    assert inserted_prereqs(run_plan(PROF["On-track"], CAT, "astar", 18)) == set()


def test_course_level():
    assert course_level("CS201") == 201 and course_level("GEN") == 0


def test_top_pruned_sorted_by_count_then_code():
    log = [RuleResult("B", False, "PRUNED", ""), RuleResult("A", False, "PREREQ", ""),
           RuleResult("B", False, "OFFERING", ""), RuleResult("C", True, "OK", "")]
    assert top_pruned(log) == [("B", 2), ("A", 1)]


def test_summarize_plan(transfer):
    text = summarize(transfer)
    assert "**4 terms, 39 credits** via A*" in text
    assert "nodes expanded" in text and "Most held-back courses" in text


def test_summarize_infeasible():
    result = PlanResult([], [RuleResult("PLAN", False, "INFEASIBLE", "no plan within 16 terms")],
                        {"expanded": 3, "generated": 5, "ms": 1.0, "cost": 0.0}, "bfs")
    assert summarize(result).startswith("**No plan (BFS).** no plan within 16 terms.")
