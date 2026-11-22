"""Production rules over the course knowledge base.

Every check returns a RuleResult so the UI can show exactly which rule fired and why.
"""

from itertools import combinations

from domain.models import Course, PlanState, RuleResult, StudentProfile

TERMS = ("fall", "spring")
REQUIRED_CATEGORIES = ("math", "core")


def term_of(start_term: str, term_index: int) -> str:
    """Return the term name ("fall"/"spring") for a 0-based term index."""
    return TERMS[(TERMS.index(start_term) + term_index) % 2]


def check_eligibility(course: Course, state: PlanState, start_term: str) -> RuleResult:
    """Apply PREREQ then OFFERING to one course in the state's current term."""
    missing = [p for p in course.prereqs if p not in state.completed]
    if missing:
        return RuleResult(course.code, False, "PREREQ",
                          f"missing prerequisite(s): {', '.join(missing)}")
    term = term_of(start_term, state.term_index)
    if term not in course.offered:
        return RuleResult(course.code, False, "OFFERING", f"not offered in {term}")
    detail = "no prerequisites"
    if course.prereqs:
        detail = f"{' ∧ '.join(f'Completed({p})' for p in course.prereqs)} ⇒ Eligible"
    if course.coreqs:
        detail += f" (corequisite(s): {', '.join(course.coreqs)})"
    return RuleResult(course.code, True, "OK", detail)


def check_schedule(combo: tuple[Course, ...], max_credits: int) -> list[RuleResult]:
    """Return every CREDIT_CAP and CONFLICT violation in a set of courses."""
    violations: list[RuleResult] = []
    total = sum(c.credits for c in combo)
    if total > max_credits:
        codes = ", ".join(c.code for c in combo)
        violations.append(RuleResult(codes, False, "CREDIT_CAP",
                                     f"{total} credits exceeds cap of {max_credits}"))
    for a, b in combinations(combo, 2):
        for slot in sorted(set(a.slots) & set(b.slots)):
            violations.append(RuleResult(f"{a.code}/{b.code}", False, "CONFLICT",
                                         f"both meet {slot}"))
    return violations


def required_courses_for(profile: StudentProfile, catalog: dict[str, Course]) -> frozenset[str]:
    """Math, core, and target-track courses, closed under prerequisites."""
    required = {
        code for code, c in catalog.items()
        if c.category in REQUIRED_CATEGORIES
        or (c.category == "track" and c.track == profile.target_track)
    }
    frontier = list(required)
    while frontier:
        for p in catalog[frontier.pop()].prereqs:
            if p in catalog and p not in required:
                required.add(p)
                frontier.append(p)
    return frozenset(required)


def elective_credits(completed: frozenset[str], catalog: dict[str, Course]) -> int:
    """Total credits of completed elective courses."""
    return sum(catalog[c].credits for c in completed
               if c in catalog and catalog[c].category == "elective")


def goal_reached(state: PlanState, profile: StudentProfile, catalog: dict[str, Course]) -> bool:
    """True iff all required courses are done and the elective credit target is met."""
    return (required_courses_for(profile, catalog) <= state.completed
            and elective_credits(state.completed, catalog) >= profile.elective_credits_required)


def check_relevance(course: Course, state: PlanState, profile: StudentProfile,
                    catalog: dict[str, Course]) -> RuleResult:
    """Return OK if the course still advances the goal, else a PRUNED result."""
    if course.code in state.completed:
        return RuleResult(course.code, False, "PRUNED", "already completed")
    if course.code in required_courses_for(profile, catalog):
        return RuleResult(course.code, True, "OK", f"required for track {profile.target_track}")
    if course.category == "elective":
        have = elective_credits(state.completed, catalog)
        need = profile.elective_credits_required
        if have < need:
            return RuleResult(course.code, True, "OK", f"elective credits {have}/{need}")
        return RuleResult(course.code, False, "PRUNED",
                          f"elective credits already satisfied ({have}/{need})")
    return RuleResult(course.code, False, "PRUNED",
                      f"not needed for track {profile.target_track}")


def is_relevant(course: Course, state: PlanState, profile: StudentProfile,
                catalog: dict[str, Course]) -> bool:
    """Boolean form of check_relevance, for use as a successor filter."""
    return check_relevance(course, state, profile, catalog).ok
