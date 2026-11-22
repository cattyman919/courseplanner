"""Tests for the production-rule layer."""

import pytest

from domain.catalog import CATALOG
from domain.models import PlanState
from domain.profiles import PROFILES
from reasoning.rules import (
    check_eligibility,
    check_relevance,
    check_schedule,
    goal_reached,
    required_courses_for,
    term_of,
)

CAT = {c.code: c for c in CATALOG}
PROF = {p.name: p for p in PROFILES}


def state(*codes: str, term_index: int = 0) -> PlanState:
    return PlanState(frozenset(codes), term_index)


def test_term_alternates():
    assert [term_of("fall", i) for i in range(3)] == ["fall", "spring", "fall"]
    assert term_of("spring", 1) == "fall"


def test_missing_prereq_fires_prereq():
    r = check_eligibility(CAT["CS301"], state("CS201"), "fall")
    assert (r.rule, r.ok) == ("PREREQ", False)
    assert "MATH210" in r.detail and "CS201" not in r.detail


def test_wrong_term_fires_offering():
    r = check_eligibility(CAT["CS210"], state("CS101"), "fall")
    assert (r.rule, r.ok) == ("OFFERING", False)
    assert r.detail == "not offered in fall"
    assert check_eligibility(CAT["CS210"], state("CS101", term_index=1), "fall").ok


def test_prereq_checked_before_offering():
    assert check_eligibility(CAT["CS210"], state(), "fall").rule == "PREREQ"


def test_eligible_is_ok_with_chain_detail():
    r = check_eligibility(CAT["CS301"], state("CS201", "MATH210"), "fall")
    assert (r.rule, r.ok) == ("OK", True)
    assert "Completed(CS201) ∧ Completed(MATH210)" in r.detail


def test_shared_slot_fires_conflict():
    out = check_schedule((CAT["MATH210"], CAT["CS210"]), 18)
    assert [r.rule for r in out] == ["CONFLICT"]
    assert "MW 10:00-11:30" in out[0].detail and out[0].subject == "MATH210/CS210"


def test_over_cap_fires_credit_cap():
    combo = (CAT["CS101"], CAT["MATH101"], CAT["GE101"])  # 11 credits, no clashes
    assert [r.rule for r in check_schedule(combo, 10)] == ["CREDIT_CAP"]
    assert check_schedule(combo, 11) == []


def test_all_violations_reported():
    combo = (CAT["MATH210"], CAT["CS210"], CAT["AI401"])
    rules = [r.rule for r in check_schedule(combo, 6)]
    assert rules.count("CONFLICT") == 3 and "CREDIT_CAP" in rules


def test_required_courses_for_ai():
    req = required_courses_for(PROF["On-track"], CAT)
    assert {"AI320", "AI330", "AI401", "CS301", "MATH301"} <= req
    assert not req & {"SYS320", "TH320", "GE101", "CS350"}


@pytest.mark.parametrize("profile_name", ["On-track", "Transfer", "Heavy electives"])
def test_goal_needs_cores_and_electives(profile_name):
    p = PROF[profile_name]
    req = required_courses_for(p, CAT)
    electives = ("CS350", "CS360", "CS390", "CS380")
    assert not goal_reached(state(*req), p, CAT)
    assert not goal_reached(state(*electives), p, CAT)
    assert goal_reached(state(*req, *electives), p, CAT)


def test_relevance_prunes_unneeded():
    p = PROF["On-track"]
    r = check_relevance(CAT["GE102"], state(), p, CAT)
    assert (r.rule, r.ok, r.detail) == ("PRUNED", False, "not needed for track ai")
    assert not check_relevance(CAT["SYS320"], state(), p, CAT).ok
    assert check_relevance(CAT["CS350"], state(), p, CAT).ok
    done = state("CS350", "CS360", "CS390")
    assert "already satisfied" in check_relevance(CAT["CS370"], done, p, CAT).detail
    assert check_relevance(CAT["CS101"], state("CS101"), p, CAT).detail == "already completed"
