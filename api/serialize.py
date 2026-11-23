"""Turn domain and reasoning objects into plain JSON-ready dicts.

The browser never re-implements a rule: every verdict, cost, and status it shows is
computed here, in Python, by the same functions the tests exercise.
"""

from domain.models import Course, PlanResult, RuleResult, StudentProfile
from reasoning.advisor import Progress, TermCheck
from reasoning.explain import ALGORITHM_NAMES, inserted_prereqs, top_pruned
from reasoning.rules import MISSING_PREFIX, term_label
from reasoning.trace import ALGORITHM_IDEAS, SearchTrace, node_title

# Status a node takes when an event of this kind happens (see reasoning.trace.statuses_at).
EVENT_STATUS = {"start": "frontier", "push": "frontier", "expand": "current",
                "duplicate": "skipped", "worse": "skipped", "stale": "stale",
                "limit": "limit", "goal": "goal"}


def course(c: Course) -> dict:
    return {"code": c.code, "title": c.title, "credits": c.credits,
            "prereqs": list(c.prereqs), "coreqs": list(c.coreqs), "offered": list(c.offered),
            "slots": list(c.slots), "category": c.category, "track": c.track}


def profile(p: StudentProfile) -> dict:
    return {"name": p.name, "completed": sorted(p.completed), "target_track": p.target_track,
            "max_credits": p.max_credits, "start_term": p.start_term,
            "elective_credits_required": p.elective_credits_required}


def missing(r: RuleResult) -> list[str]:
    """Course codes named as missing prerequisites in a PREREQ result."""
    if r.rule != "PREREQ" or MISSING_PREFIX not in r.detail:
        return []
    return [x.strip() for x in r.detail.split(MISSING_PREFIX, 1)[1].split(",")]


def rule(r: RuleResult) -> dict:
    return {"subject": r.subject, "ok": r.ok, "rule": r.rule, "detail": r.detail,
            "missing": missing(r)}


def plan(result: PlanResult, start_term: str, offset: int = 0) -> dict:
    """A plan with labelled terms; `offset` shifts labels for plans that start mid-way."""
    terms = [{"label": term_label(start_term, offset + i), "courses": [c.code for c in t],
              "credits": sum(c.credits for c in t)} for i, t in enumerate(result.semesters)]
    infeasible = next((r.detail for r in result.log if r.rule == "INFEASIBLE"), None)
    return {
        "algorithm": result.algorithm, "algorithm_name": ALGORITHM_NAMES[result.algorithm],
        "terms": terms, "total_credits": sum(t["credits"] for t in terms),
        "log": [rule(r) for r in result.log], "stats": result.stats,
        "inserted": sorted(inserted_prereqs(result)),
        "top_pruned": [{"code": c, "count": n} for c, n in top_pruned(result.log)],
        "infeasible": infeasible,
    }


def trace(t: SearchTrace) -> dict:
    nodes = []
    for n in sorted(t.nodes.values(), key=lambda n: n.id):
        title = node_title(n, t.start_term)
        nodes.append({"id": n.id, "parent": n.parent, "depth": n.term_index,
                      "term": title.partition(" +")[0].replace(" (wait)", ""),
                      "combo": list(n.combo), "g": n.g, "h": n.h, "title": title})
    events = [{"step": e.step, "kind": e.kind, "node": e.node, "text": e.text,
               "frontier": e.frontier, "closed": e.closed,
               "status": EVENT_STATUS.get(e.kind)} for e in t.events]
    return {"algorithm": t.algorithm, "algorithm_name": ALGORITHM_NAMES[t.algorithm],
            "idea": ALGORITHM_IDEAS[t.algorithm], "start_term": t.start_term,
            "nodes": nodes, "events": events, "path": list(t.path), "goal_node": t.goal_node,
            "truncated": t.truncated, "plan": plan(t.result, t.start_term)}


def term_check(check: TermCheck) -> dict:
    return {"per_course": {code: rule(r) for code, r in check.per_course.items()},
            "schedule": [rule(r) for r in check.schedule],
            "blocking": [rule(r) for r in check.blocking],
            "warnings": [rule(r) for r in check.warnings],
            "credits": check.credits, "max_credits": check.max_credits,
            "can_commit": check.can_commit}


def progress(p: Progress) -> dict:
    return {"required_left": list(p.required_left), "elective_have": p.elective_have,
            "elective_need": p.elective_need, "done": p.done}
