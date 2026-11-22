"""Record a search run event by event, so the UI can replay it step by step.

Each event changes the status of one search node. Replaying the first ``k`` events gives
the search tree as it looked after ``k`` steps: what was expanded, what is waiting in the
frontier, what was skipped, and (at the end) the goal and the solution path.
"""

from dataclasses import dataclass, field

from domain.models import Course, PlanResult, StudentProfile
from reasoning.rules import term_label
from reasoning.search import run_plan

MAX_EVENTS = 5000
ALGORITHM_IDEAS = {
    "bfs": "BFS expands states in the order they were generated (FIFO), so it finishes "
           "every 1-term plan before any 2-term plan. It ignores credits entirely.",
    "ucs": "UCS always expands the cheapest state so far (lowest g). It is optimal, but "
           "it has no idea how far the goal is, so it explores in every direction.",
    "astar": "A* expands the state with the lowest f = g + h, where h is an admissible "
             "estimate of the remaining cost. It reaches the same optimal cost as UCS "
             "while expanding fewer states.",
}


@dataclass(frozen=True)
class TraceNode:
    """One search node: the state reached after taking `combo` in term `term_index - 1`."""

    id: int
    parent: int | None
    term_index: int
    combo: tuple[str, ...]
    g: float
    h: float | None


@dataclass(frozen=True)
class TraceEvent:
    """One step of the search, with a human-readable explanation."""

    step: int
    kind: str  # start | expand | push | duplicate | worse | stale | limit | goal | exhausted
    node: int | None
    text: str
    frontier: int
    closed: int


@dataclass
class SearchTrace:
    """A full recorded run: events in order, every node created, and the final result."""

    algorithm: str
    start_term: str
    events: list[TraceEvent]
    nodes: dict[int, TraceNode]
    result: PlanResult
    goal_node: int | None = None
    truncated: bool = False
    path: list[int] = field(default_factory=list)


def node_title(node: TraceNode, start_term: str) -> str:
    """Short label: "Start" or "Fall 2026 +CS301 CS310"."""
    if node.parent is None:
        return "Start"
    term = term_label(start_term, node.term_index - 1)
    return f"{term} +{' '.join(node.combo)}" if node.combo else f"{term} (wait)"


def trace_search(profile: StudentProfile, catalog: dict[str, Course], algorithm: str,
                 max_credits: int) -> SearchTrace:
    """Run the planner with an observer and return the recorded trace."""
    events: list[TraceEvent] = []
    nodes: dict[int, TraceNode] = {}
    state = {"goal": None, "truncated": False}

    def fmt(value: float | None) -> str:
        return "–" if value is None else f"{value:.2f}"

    def observe(kind: str, data: dict) -> None:
        if len(events) >= MAX_EVENTS:
            state["truncated"] = True
            return
        node_id = data.get("node")
        if kind in ("start", "push", "duplicate", "worse"):
            nodes[node_id] = TraceNode(
                id=node_id, parent=data.get("parent"), term_index=data["state"].term_index,
                combo=tuple(data.get("combo", ())), g=data["g"], h=data.get("h"))
        node = nodes.get(node_id)
        title = node_title(node, profile.start_term) if node else ""
        if kind == "start":
            text = (f"Start with {len(profile.completed)} completed courses; "
                    f"h = {fmt(data['h'])}. The frontier holds just this state.")
        elif kind == "expand":
            g, h = data["g"], data["h"]
            f = f", f = {g + h:.2f}" if algorithm == "astar" else ""
            eligible = ", ".join(data["candidates"]) or "none"
            text = (f"Expand #{node_id} ({title}) with g = {g:.2f}{f}. "
                    f"Eligible and needed now: {eligible}.")
        elif kind == "push":
            text = (f"Generate #{node_id}: {title}. g = {data['g']:.2f}, h = {fmt(data['h'])}. "
                    "Added to the frontier.")
        elif kind == "duplicate":
            text = f"Skip #{node_id}: {title} reaches a state that was already expanded."
        elif kind == "worse":
            text = (f"Skip #{node_id}: {title} reaches a queued state that already has "
                    f"g = {data['best']:.2f} ≤ {data['g']:.2f}.")
        elif kind == "stale":
            text = f"Pop #{node_id}: already expanded via a cheaper path, so it is ignored."
        elif kind == "limit":
            text = f"Pop #{node_id}: the {node.term_index}-term limit is reached; not expanded."
        elif kind == "goal":
            state["goal"] = node_id
            text = (f"Goal test passes at #{node_id} ({title}): every requirement is met. "
                    f"Plan cost = {data['g']:.2f}.")
        else:
            text = "The frontier is empty: no plan exists within the term limit."
        events.append(TraceEvent(len(events), kind, node_id, text,
                                 data["frontier"], data["closed"]))

    result = run_plan(profile, catalog, algorithm, max_credits, observer=observe)
    trace = SearchTrace(algorithm, profile.start_term, events, nodes, result,
                        goal_node=state["goal"], truncated=state["truncated"])
    node_id = trace.goal_node
    while node_id is not None:
        trace.path.append(node_id)
        node_id = nodes[node_id].parent
    trace.path.reverse()
    return trace


def statuses_at(trace: SearchTrace, step: int) -> dict[int, str]:
    """Status of every node visible after replaying events[0..step] (inclusive).

    Statuses: frontier, current (being expanded now), expanded, skipped, stale, limit,
    goal, and path (on the solution path, once the goal has been reached).
    """
    status: dict[int, str] = {}
    for event in trace.events[:step + 1]:
        if event.node is None:
            continue
        status.update({n: "expanded" for n, s in status.items() if s == "current"})
        status[event.node] = {
            "start": "frontier", "push": "frontier", "expand": "current",
            "duplicate": "skipped", "worse": "skipped", "stale": "stale",
            "limit": "limit", "goal": "goal",
        }[event.kind]
    if trace.goal_node is not None and status.get(trace.goal_node) == "goal":
        status.update({n: "path" for n in trace.path if n != trace.goal_node})
    return status
