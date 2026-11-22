"""Explanation plumbing: build the rule log for a plan and summarise it."""

import re
from collections import Counter

from domain.models import Course, PlanResult, PlanState, RuleResult, StudentProfile
from reasoning.rules import (
    MISSING_PREFIX,
    check_eligibility,
    check_relevance,
    check_schedule,
    term_label,
)

ALGORITHM_NAMES = {"bfs": "BFS", "ucs": "UCS", "astar": "A*"}
BLOCKING_RULES = ("PRUNED", "PREREQ", "OFFERING")
UPPER_DIVISION = 300


def combo_label(start_term: str, term_index: int, combo: tuple[Course, ...]) -> str:
    """Short label for one planned term, e.g. "Fall 2026: CS301, CS310, MATH301"."""
    taken = ", ".join(c.code for c in combo) or "(no eligible courses; wait)"
    return f"{term_label(start_term, term_index)}: {taken}"


def explain_plan(semesters: list[tuple[Course, ...]], profile: StudentProfile,
                 catalog: dict[str, Course]) -> list[RuleResult]:
    """Replay a plan term by term and record, in order, every rule that fires.

    Per term: PRUNED (each course/reason once), PREREQ/OFFERING/OK for needed courses,
    CONFLICT for eligible pairs sharing a slot, then one OK row naming the bundle taken.
    """
    log: list[RuleResult] = []
    seen_prunes: set[tuple[str, str]] = set()
    state = PlanState(profile.completed, 0)
    for combo in semesters:
        label = term_label(profile.start_term, state.term_index)
        eligible: list[Course] = []
        for code, course in sorted(catalog.items()):
            if code in state.completed:
                continue
            relevance = check_relevance(course, state, profile, catalog)
            if not relevance.ok:
                if (code, relevance.detail) not in seen_prunes:
                    seen_prunes.add((code, relevance.detail))
                    log.append(relevance)
                continue
            result = check_eligibility(course, state, profile.start_term)
            log.append(RuleResult(code, result.ok, result.rule, f"{label}: {result.detail}"))
            if result.ok:
                eligible.append(course)
        for clash in check_schedule(tuple(eligible), max_credits=10**6):
            log.append(RuleResult(clash.subject, False, clash.rule,
                                  f"{label}: {clash.detail}; cannot take both"))
        credits = sum(c.credits for c in combo)
        log.append(RuleResult(label, True, "OK",
                              f"{combo_label(profile.start_term, state.term_index, combo)}"
                              f" ({credits} cr)"))
        state = PlanState(state.completed | {c.code for c in combo}, state.term_index + 1)
    return log


def missing_prereqs(log: list[RuleResult]) -> set[str]:
    """Every course code named as a missing prerequisite in a PREREQ entry."""
    missing: set[str] = set()
    for r in log:
        if r.rule == "PREREQ" and MISSING_PREFIX in r.detail:
            missing.update(x.strip() for x in r.detail.split(MISSING_PREFIX, 1)[1].split(","))
    return missing


def course_level(code: str) -> int:
    """Numeric level of a course code ("CS201" -> 201); 0 if it has no number."""
    match = re.search(r"\d+", code)
    return int(match.group()) if match else 0


def inserted_prereqs(result: PlanResult) -> set[str]:
    """Planned lower-division courses that the log shows were missing prerequisites.

    These are catch-up courses (e.g. a transfer student's gaps), flagged in the UI.
    """
    planned = {c.code for term in result.semesters for c in term}
    return {c for c in planned & missing_prereqs(result.log) if course_level(c) < UPPER_DIVISION}


def top_pruned(log: list[RuleResult], n: int = 3) -> list[tuple[str, int]]:
    """Courses held back most often (PRUNED, PREREQ, OFFERING), ties broken by code."""
    counts = Counter(r.subject for r in log if not r.ok and r.rule in BLOCKING_RULES)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def summarize(result: PlanResult) -> str:
    """Markdown summary: term count, credits, algorithm, effort, most-pruned courses."""
    name = ALGORITHM_NAMES.get(result.algorithm, result.algorithm)
    stats = result.stats
    effort = (f"{stats.get('expanded', 0)} nodes expanded, {stats.get('generated', 0)}"
              f" generated in {stats.get('ms', 0):.2f} ms")
    if not result.semesters:
        reason = next((r.detail for r in result.log if r.rule == "INFEASIBLE"),
                      "goal already satisfied")
        return f"**No plan ({name}).** {reason}.\n\n- {effort}"
    credits = sum(c.credits for term in result.semesters for c in term)
    headline = (f"**{len(result.semesters)} terms, {credits} credits** via {name}"
                f" (cost {stats.get('cost', 0):g}).")
    lines = [
        headline,
        "",
        f"- {effort}",
    ]
    pruned = top_pruned(result.log)
    if pruned:
        lines.append("- Most held-back courses: "
                     + ", ".join(f"{code} ({k}×)" for code, k in pruned))
    return "\n".join(lines)
