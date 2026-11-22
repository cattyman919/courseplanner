"""State-space search over PlanState: BFS and UCS share one best-first driver.

Each edge is one term. A successor applies one bundle from ``valid_combos`` to the courses
that are both eligible (PREREQ, OFFERING) and relevant (not PRUNED). If nothing can be
taken this term, the only successor waits a term.
"""

import heapq
import time
from collections import deque
from collections.abc import Callable, Iterator

from domain.models import Course, PlanResult, PlanState, RuleResult, StudentProfile
from reasoning.combos import valid_combos
from reasoning.rules import (
    check_eligibility,
    check_relevance,
    check_schedule,
    elective_credits,
    goal_reached,
    term_label,
    term_of,
)

MAX_TERMS = 16
ALGORITHMS = ("bfs", "ucs")

StateKey = tuple[frozenset[str], str]
Combo = tuple[Course, ...]


def state_key(state: PlanState, start_term: str) -> StateKey:
    """Identify a state by completed set and the actual current term name."""
    return state.completed, term_of(start_term, state.term_index)


def candidates(state: PlanState, profile: StudentProfile,
               catalog: dict[str, Course]) -> list[Course]:
    """Courses that are relevant to the goal and eligible this term, sorted by code."""
    return [
        c for code, c in sorted(catalog.items())
        if check_relevance(c, state, profile, catalog).ok
        and check_eligibility(c, state, profile.start_term).ok
    ]


def successors(state: PlanState, profile: StudentProfile, catalog: dict[str, Course],
               max_credits: int) -> Iterator[tuple[Combo, PlanState]]:
    """Yield (bundle, next_state) pairs; an empty bundle means waiting one term."""
    need = profile.elective_credits_required - elective_credits(state.completed, catalog)
    combos, _ = valid_combos(candidates(state, profile, catalog), max_credits,
                             elective_credits_needed=max(need, 0))
    if not combos:
        yield (), PlanState(state.completed, state.term_index + 1)
        return
    for combo in combos:
        yield combo, PlanState(state.completed | {c.code for c in combo}, state.term_index + 1)


def edge_cost(algorithm: str, combo: Combo) -> float:
    """BFS counts terms; UCS (and A*) charge 1 + 0.05 per credit for each term."""
    if algorithm == "bfs":
        return 1.0
    return 1.0 + 0.05 * sum(c.credits for c in combo)


def _frontier(algorithm: str) -> tuple[Callable, Callable, Callable]:
    """Return (push, pop, size) for a FIFO queue (BFS) or a priority queue."""
    if algorithm == "bfs":
        queue: deque = deque()
        return (lambda prio, item: queue.append(item), queue.popleft, lambda: len(queue))
    heap: list = []
    counter = iter(range(1 << 62))
    return (lambda prio, item: heapq.heappush(heap, (prio, next(counter), item)),
            lambda: heapq.heappop(heap)[2], lambda: len(heap))


def explain_plan(semesters: list[Combo], profile: StudentProfile,
                 catalog: dict[str, Course]) -> list[RuleResult]:
    """Replay the chosen plan term by term and record every rule that fires.

    Each course's PRUNED reason is logged once (first term it applies), to keep it readable.
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
        for clash in check_schedule(tuple(eligible), 10**6):
            log.append(RuleResult(clash.subject, False, clash.rule,
                                  f"{label}: {clash.detail}; cannot take both"))
        taken = ", ".join(c.code for c in combo) or "(no eligible courses; wait)"
        credits = sum(c.credits for c in combo)
        log.append(RuleResult(label, True, "OK", f"{label}: {taken} ({credits} cr)"))
        state = PlanState(state.completed | {c.code for c in combo}, state.term_index + 1)
    return log


def run_plan(profile: StudentProfile, catalog: dict[str, Course], algorithm: str,
             max_credits: int) -> PlanResult:
    """Search for a term-by-term plan that reaches the profile's goal."""
    if algorithm not in ALGORITHMS:
        raise ValueError(f"unknown algorithm {algorithm!r}; expected one of {ALGORITHMS}")
    started = time.perf_counter()
    start = PlanState(profile.completed, 0)
    push, pop, size = _frontier(algorithm)
    best: dict[StateKey, float] = {state_key(start, profile.start_term): 0.0}
    parent: dict[StateKey, tuple[StateKey, Combo] | None] = {
        state_key(start, profile.start_term): None}
    closed: set[StateKey] = set()
    push(0.0, (0.0, start))
    expanded = generated = 0

    while size():
        cost, state = pop()
        key = state_key(state, profile.start_term)
        if key in closed:
            continue
        closed.add(key)
        if goal_reached(state, profile, catalog):
            semesters = _path(parent, key)
            return PlanResult(
                semesters=[list(c) for c in semesters],
                log=explain_plan(semesters, profile, catalog),
                stats=_stats(expanded, generated, started, cost),
                algorithm=algorithm,
            )
        if state.term_index >= MAX_TERMS:
            continue
        expanded += 1
        for combo, nxt in successors(state, profile, catalog, max_credits):
            generated += 1
            nkey = state_key(nxt, profile.start_term)
            ncost = cost + edge_cost(algorithm, combo)
            if nkey in closed or ncost >= best.get(nkey, float("inf")):
                continue
            best[nkey] = ncost
            parent[nkey] = (key, combo)
            push(ncost, (ncost, nxt))

    log = [r for r in explain_plan([()], profile, catalog) if r.rule == "PRUNED"]
    log.append(RuleResult("PLAN", False, "INFEASIBLE",
                          f"no plan within {MAX_TERMS} terms at {max_credits} credits/term"))
    return PlanResult([], log, _stats(expanded, generated, started, 0.0), algorithm)


def _path(parent: dict[StateKey, tuple[StateKey, Combo] | None], key: StateKey) -> list[Combo]:
    """Walk parent links back to the start and return the bundles in order."""
    combos: list[Combo] = []
    link = parent[key]
    while link is not None:
        key, combo = link
        combos.append(combo)
        link = parent[key]
    return combos[::-1]


def _stats(expanded: int, generated: int, started: float, cost: float) -> dict:
    """Pack search statistics in the shape PlanResult.stats expects."""
    return {"expanded": expanded, "generated": generated,
            "ms": round((time.perf_counter() - started) * 1000, 2), "cost": round(cost, 4)}
