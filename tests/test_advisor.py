"""Tests for advisor mode: checking student-chosen terms."""

from domain.catalog import CATALOG
from domain.profiles import PROFILES
from reasoning.advisor import (
    available_now,
    check_term,
    course_verdict,
    progress,
    state_after,
    suggest_rest,
)
from reasoning.rules import check_eligibility

CAT = {c.code: c for c in CATALOG}
PROF = {p.name: p for p in PROFILES}
ON_TRACK = PROF["On-track"]
TRANSFER = PROF["Transfer"]


def test_state_after_accumulates_terms():
    s = state_after(ON_TRACK, [["CS301"], ["AI320"]])
    assert {"CS301", "AI320"} <= s.completed and s.term_index == 2


def test_verdict_blocks_missing_prereq():
    r = course_verdict(CAT["AI320"], state_after(ON_TRACK, []), ON_TRACK, CAT)
    assert (r.rule, r.ok) == ("PREREQ", False) and "CS301" in r.detail


def test_verdict_blocks_wrong_term():
    fall_again = state_after(ON_TRACK, [["CS301"], []])  # term 2 is fall; AI320 is spring-only
    r = course_verdict(CAT["AI320"], fall_again, ON_TRACK, CAT)
    assert (r.rule, r.ok) == ("OFFERING", False)


def test_verdict_warns_when_not_needed():
    r = course_verdict(CAT["SYS330"], state_after(ON_TRACK, []), ON_TRACK, CAT)
    assert r.rule == "PRUNED" and "not needed" in r.detail


def test_good_term_can_commit():
    check = check_term(["CS301", "CS310", "MATH301"], state_after(ON_TRACK, []), ON_TRACK, CAT, 18)
    assert check.can_commit and check.credits == 10 and not check.blocking


def test_conflict_blocks_commit():
    check = check_term(["MATH210", "CS210"], state_after(TRANSFER, []), TRANSFER, CAT, 18)
    assert not check.can_commit
    assert [r.rule for r in check.blocking] == ["CONFLICT"]


def test_credit_cap_blocks_commit():
    picks = ["CS301", "CS310", "CS350", "CS360", "MATH301"]  # 16 credits
    check = check_term(picks, state_after(ON_TRACK, []), ON_TRACK, CAT, 12)
    assert not check.can_commit and any(r.rule == "CREDIT_CAP" for r in check.blocking)


def test_unneeded_course_warns_but_allows_commit():
    check = check_term(["CS301", "SYS330"], state_after(ON_TRACK, []), ON_TRACK, CAT, 18)
    assert check.can_commit and [r.subject for r in check.warnings] == ["SYS330"]


def test_empty_term_cannot_commit():
    assert not check_term([], state_after(ON_TRACK, []), ON_TRACK, CAT, 18).can_commit


def test_available_now_all_eligible():
    state = state_after(TRANSFER, [])
    codes = [c.code for c in available_now(state, TRANSFER, CAT)]
    assert codes == ["CS201", "CS210", "CS360", "MATH210"]
    assert all(check_eligibility(CAT[c], state, TRANSFER.start_term).ok for c in codes)


def test_progress_counts_down():
    start = progress(state_after(ON_TRACK, []), ON_TRACK, CAT)
    assert "AI401" in start.required_left and start.elective_have == 0 and not start.done
    end_terms = [["CS301", "CS310", "CS350", "CS360", "MATH301"], ["AI320", "AI330", "CS390"],
                 ["AI401"]]
    assert progress(state_after(ON_TRACK, end_terms), ON_TRACK, CAT).done


def test_suggest_rest_continues_from_current_term():
    terms = [["CS301", "CS310", "MATH301"]]
    plan = suggest_rest(state_after(ON_TRACK, terms), ON_TRACK, CAT, 18)
    assert plan.semesters
    assert "AI320" in {c.code for c in plan.semesters[0]}  # spring-only: plan starts in spring
    for term in plan.semesters:
        state = state_after(ON_TRACK, terms)
        for course in term:
            assert check_eligibility(course, state, ON_TRACK.start_term).ok, course.code
        terms.append([c.code for c in term])
    assert progress(state_after(ON_TRACK, terms), ON_TRACK, CAT).done
