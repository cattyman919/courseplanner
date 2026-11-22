"""Advisor mode: check a student's own course choices with the same production rules.

The student plays term by term. For each pick the rule engine answers with a verdict
(OK, a blocking PREREQ/OFFERING, or an advisory PRUNED), checks the term as a whole
(CREDIT_CAP, CONFLICT), and can suggest the rest of the plan with the search engine.
"""

from dataclasses import dataclass, replace

from domain.models import Course, PlanResult, PlanState, RuleResult, StudentProfile
from reasoning.rules import (
    check_eligibility,
    check_relevance,
    check_schedule,
    elective_credits,
    goal_reached,
    required_courses_for,
    term_of,
)
from reasoning.search import candidates, run_plan

BLOCKING = ("PREREQ", "OFFERING", "CREDIT_CAP", "CONFLICT")


@dataclass(frozen=True)
class TermCheck:
    """Verdict on a set of picks for one term."""

    per_course: dict[str, RuleResult]
    schedule: list[RuleResult]
    credits: int
    max_credits: int

    @property
    def blocking(self) -> list[RuleResult]:
        """Every rule failure that forbids committing the term."""
        return [r for r in [*self.per_course.values(), *self.schedule]
                if not r.ok and r.rule in BLOCKING]

    @property
    def warnings(self) -> list[RuleResult]:
        """Advisory findings (courses not needed for the goal); allowed but flagged."""
        return [r for r in self.per_course.values() if r.rule == "PRUNED"]

    @property
    def can_commit(self) -> bool:
        """True if at least one course is picked and no blocking rule fired."""
        return bool(self.per_course) and not self.blocking


def state_after(profile: StudentProfile, terms: list[list[str]]) -> PlanState:
    """The state reached after the student's committed terms."""
    done = set(profile.completed)
    for term in terms:
        done.update(term)
    return PlanState(frozenset(done), len(terms))


def course_verdict(course: Course, state: PlanState, profile: StudentProfile,
                   catalog: dict[str, Course]) -> RuleResult:
    """Eligibility first (PREREQ, OFFERING); if eligible, flag it if it is not needed."""
    eligibility = check_eligibility(course, state, profile.start_term)
    if not eligibility.ok:
        return eligibility
    relevance = check_relevance(course, state, profile, catalog)
    return eligibility if relevance.ok else relevance


def check_term(picks: list[str], state: PlanState, profile: StudentProfile,
               catalog: dict[str, Course], max_credits: int) -> TermCheck:
    """Check every pick and the term as a whole."""
    chosen = tuple(catalog[c] for c in sorted(picks))
    return TermCheck(
        per_course={c.code: course_verdict(c, state, profile, catalog) for c in chosen},
        schedule=check_schedule(chosen, max_credits),
        credits=sum(c.credits for c in chosen),
        max_credits=max_credits,
    )


def available_now(state: PlanState, profile: StudentProfile,
                  catalog: dict[str, Course]) -> list[Course]:
    """Courses that are eligible this term and still needed (what the planner considers)."""
    return candidates(state, profile, catalog)


@dataclass(frozen=True)
class Progress:
    """How far the student is from graduating in their track."""

    required_left: tuple[str, ...]
    elective_have: int
    elective_need: int
    done: bool


def progress(state: PlanState, profile: StudentProfile,
             catalog: dict[str, Course]) -> Progress:
    """Remaining required courses and elective credits."""
    return Progress(
        required_left=tuple(sorted(required_courses_for(profile, catalog) - state.completed)),
        elective_have=elective_credits(state.completed, catalog),
        elective_need=profile.elective_credits_required,
        done=goal_reached(state, profile, catalog),
    )


def suggest_rest(state: PlanState, profile: StudentProfile, catalog: dict[str, Course],
                 max_credits: int, algorithm: str = "astar") -> PlanResult:
    """Plan the remaining terms from the student's current state.

    The returned semesters start at the current term; their labels start at index
    ``state.term_index`` relative to the student's original start term.
    """
    here = replace(profile, completed=state.completed,
                   start_term=term_of(profile.start_term, state.term_index))
    return run_plan(here, catalog, algorithm, max_credits)
