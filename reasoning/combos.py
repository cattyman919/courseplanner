"""Generate the course bundles a student could take in one term.

DFS over skip/take decisions with constraint pruning (credit cap, slot clashes). Only
*maximal* bundles are emitted: ones where no further eligible course could be added.
A non-maximal bundle never finishes sooner, so dropping it keeps the branching small
without losing the fewest-terms plan.
"""

from domain.models import Course

MAX_COMBOS = 64


def valid_combos(eligible: list[Course], max_credits: int, min_credits: int = 9,
                 elective_credits_needed: int | None = None,
                 ) -> tuple[list[tuple[Course, ...]], bool]:
    """Return (maximal clash-free bundles within the credit cap, truncated flag).

    Bundles below ``min_credits`` are returned only when no bundle reaches it (e.g. the
    last course of a plan, or a student blocked mid-chain). If ``elective_credits_needed``
    is given, electives stop being addable once the bundle covers that many credits.
    At most ``MAX_COMBOS`` bundles are returned; ``truncated`` says whether more existed.
    """
    courses = sorted(eligible, key=lambda c: c.code)
    results: list[tuple[Course, ...]] = []
    truncated = False

    def addable(course: Course, credits: int, slots: set[str], elective: int) -> bool:
        if credits + course.credits > max_credits or slots & set(course.slots):
            return False
        return not (course.category == "elective" and elective_credits_needed is not None
                    and elective >= elective_credits_needed)

    def dfs(i: int, taken: list[Course], credits: int, slots: set[str], elective: int) -> None:
        nonlocal truncated
        if truncated:
            return
        if i == len(courses):
            if taken and not any(addable(c, credits, slots, elective)
                                 for c in courses if c not in taken):
                if len(results) == MAX_COMBOS:
                    truncated = True
                else:
                    results.append(tuple(taken))
            return
        course = courses[i]
        if addable(course, credits, slots, elective):
            taken.append(course)
            dfs(i + 1, taken, credits + course.credits, slots | set(course.slots),
                elective + (course.credits if course.category == "elective" else 0))
            taken.pop()
        dfs(i + 1, taken, credits, slots, elective)

    dfs(0, [], 0, set(), 0)
    full = [c for c in results if sum(x.credits for x in c) >= min_credits]
    return (full or results), truncated
