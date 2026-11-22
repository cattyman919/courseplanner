"""State-space search over PlanState: BFS, UCS, and A* share one best-first driver.

Each edge is one term. A successor applies one bundle from ``valid_combos`` to the courses
that are both eligible (PREREQ, OFFERING) and relevant (not PRUNED). If nothing can be
taken this term, the only successor waits a term.
"""

import heapq
import time
from collections import deque
from collections.abc import Callable, Iterator
from math import ceil

from domain.models import Course, PlanResult, PlanState, RuleResult, StudentProfile
from reasoning.combos import valid_combos
from reasoning.explain import explain_plan
from reasoning.rules import (
    check_eligibility,
    check_relevance,
    elective_credits,
    goal_reached,
    required_courses_for,
    term_of,
)

MAX_TERMS = 16
ALGORITHMS = ("bfs", "ucs", "astar")
CREDIT_WEIGHT = 0.05

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
    """BFS counts terms; UCS and A* charge 1 + 0.05 per credit for each term."""
    if algorithm == "bfs":
        return 1.0
    return 1.0 + CREDIT_WEIGHT * sum(c.credits for c in combo)


def longest_prereq_chain(remaining: frozenset[str], completed: frozenset[str],
                         catalog: dict[str, Course]) -> int:
    """Length of the longest chain of not-yet-completed prerequisites among `remaining`.

    Each link needs its own term, so this is a lower bound on the terms still required.
    """
    memo: dict[str, int] = {}

    def depth(code: str) -> int:
        if code not in memo:
            open_prereqs = [p for p in catalog[code].prereqs
                            if p in catalog and p not in completed]
            memo[code] = 1 + max((depth(p) for p in open_prereqs), default=0)
        return memo[code]

    return max((depth(c) for c in sorted(remaining) if c in catalog), default=0)


def heuristic(state: PlanState, profile: StudentProfile, catalog: dict[str, Course],
              max_credits: int) -> float:
    """Admissible, consistent estimate of the remaining `1 + 0.05·credits` cost.

    Terms left ≥ max(credit bound, prerequisite-depth bound), and each term costs ≥ 1.
    Every remaining required credit, and every missing elective credit, is charged 0.05
    exactly once, so the estimate never exceeds the true remaining cost.
    """
    remaining = required_courses_for(profile, catalog) - state.completed
    elective_need = max(0, profile.elective_credits_required
                        - elective_credits(state.completed, catalog))
    credit_need = sum(catalog[c].credits for c in remaining) + elective_need
    credit_bound = ceil(credit_need / max_credits)
    depth_bound = longest_prereq_chain(remaining, state.completed, catalog)
    return max(credit_bound, depth_bound) + CREDIT_WEIGHT * credit_need


def _frontier(algorithm: str) -> tuple[Callable, Callable, Callable]:
    """Return (push, pop, size) for a FIFO queue (BFS) or a priority queue."""
    if algorithm == "bfs":
        queue: deque = deque()
        return (lambda prio, item: queue.append(item), queue.popleft, lambda: len(queue))
    heap: list = []
    counter = iter(range(1 << 62))
    return (lambda prio, item: heapq.heappush(heap, (prio, next(counter), item)),
            lambda: heapq.heappop(heap)[2], lambda: len(heap))


Observer = Callable[[str, dict], None]


def run_plan(profile: StudentProfile, catalog: dict[str, Course], algorithm: str,
             max_credits: int, observer: Observer | None = None) -> PlanResult:
    """Search for a term-by-term plan that reaches the profile's goal.

    If ``observer`` is given it is called as ``observer(kind, data)`` for every search
    event (start, expand, push, duplicate, worse, stale, limit, goal, exhausted); see
    ``reasoning.trace``. Each search node gets an integer id; the start node is 0.
    """
    if algorithm not in ALGORITHMS:
        raise ValueError(f"unknown algorithm {algorithm!r}; expected one of {ALGORITHMS}")
    started = time.perf_counter()
    start = PlanState(profile.completed, 0)
    push, pop, size = _frontier(algorithm)
    best: dict[StateKey, float] = {state_key(start, profile.start_term): 0.0}
    parent: dict[StateKey, tuple[StateKey, Combo] | None] = {
        state_key(start, profile.start_term): None}
    closed: set[StateKey] = set()
    node_ids = iter(range(1 << 62))

    def h(s: PlanState) -> float:
        return heuristic(s, profile, catalog, max_credits) if algorithm == "astar" else 0.0

    def notify(kind: str, **data: object) -> None:
        if observer is not None:
            observer(kind, {**data, "frontier": size(), "closed": len(closed)})

    root = next(node_ids)
    push(h(start), (0.0, start, root))
    notify("start", node=root, state=start, g=0.0, h=h(start))
    expanded = generated = 0

    while size():
        cost, state, node = pop()
        key = state_key(state, profile.start_term)
        if key in closed:
            notify("stale", node=node, state=state, g=cost)
            continue
        closed.add(key)
        if goal_reached(state, profile, catalog):
            semesters = _path(parent, key)
            notify("goal", node=node, state=state, g=cost)
            return PlanResult(
                semesters=[list(c) for c in semesters],
                log=explain_plan(semesters, profile, catalog),
                stats=_stats(expanded, generated, started, cost),
                algorithm=algorithm,
            )
        if state.term_index >= MAX_TERMS:
            notify("limit", node=node, state=state, g=cost)
            continue
        expanded += 1
        if observer is not None:
            notify("expand", node=node, state=state, g=cost, h=h(state),
                   candidates=[c.code for c in candidates(state, profile, catalog)])
        for combo, nxt in successors(state, profile, catalog, max_credits):
            generated += 1
            child = next(node_ids)
            nkey = state_key(nxt, profile.start_term)
            ncost = cost + edge_cost(algorithm, combo)
            info = {"node": child, "parent": node, "combo": [c.code for c in combo],
                    "state": nxt, "g": ncost}
            if nkey in closed:
                notify("duplicate", **info)
                continue
            if ncost >= best.get(nkey, float("inf")):
                notify("worse", **info, best=best[nkey])
                continue
            best[nkey] = ncost
            parent[nkey] = (key, combo)
            child_h = h(nxt)
            push(ncost + child_h, (ncost, nxt, child))
            notify("push", **info, h=child_h)

    notify("exhausted")
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
