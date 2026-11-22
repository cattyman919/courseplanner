"""In-memory domain types used by the reasoning engine."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Course:
    """A catalog course: the atomic fact the rule layer reasons about."""

    code: str
    title: str
    credits: int
    prereqs: tuple[str, ...] = ()
    coreqs: tuple[str, ...] = ()
    offered: tuple[str, ...] = ("fall", "spring")
    slots: tuple[str, ...] = ()
    category: str = "core"  # "core" | "track" | "elective" | "gened" | "math"
    track: str | None = None  # "ai" | "systems" | "theory" | None


@dataclass(frozen=True)
class StudentProfile:
    """A student's starting facts and planning goals."""

    name: str
    completed: frozenset[str]
    target_track: str
    max_credits: int = 18
    start_term: str = "fall"
    elective_credits_required: int = 9


@dataclass(frozen=True)
class PlanState:
    """A search node: courses completed so far and how many terms have elapsed."""

    completed: frozenset[str]
    term_index: int


@dataclass(frozen=True)
class RuleResult:
    """One fired (or failed) rule, recorded in the inference log."""

    subject: str
    ok: bool
    rule: str  # "PREREQ" | "OFFERING" | "CREDIT_CAP" | "CONFLICT" | "PRUNED" | "OK" | "INFEASIBLE"
    detail: str


@dataclass
class PlanResult:
    """The output of a planner run."""

    semesters: list[list[Course]]
    log: list[RuleResult]
    stats: dict  # {"expanded": int, "generated": int, "ms": float, "cost": float}
    algorithm: str
