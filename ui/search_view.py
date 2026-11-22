"""'Watch the Search' tab: replay a recorded search event by event, like a debugger.

Step / Back / Play / Run to end move through the trace; the search tree, the frontier
size, and the event log update at every step.
"""

from collections.abc import Callable

import streamlit as st

from reasoning.explain import ALGORITHM_NAMES
from reasoning.search import ALGORITHMS
from reasoning.trace import ALGORITHM_IDEAS, SearchTrace, node_title, statuses_at

STYLE = {  # status -> (fill, border, extra style)
    "frontier": ("#ffffff", "#4c78d8", ""),
    "current": ("#ffb347", "#c46b00", ",bold"),
    "expanded": ("#cfe0fb", "#4c78d8", ""),
    "skipped": ("#eeeeee", "#aaaaaa", ",dashed"),
    "stale": ("#eeeeee", "#aaaaaa", ",dashed"),
    "limit": ("#eeeeee", "#aaaaaa", ",dashed"),
    "path": ("#c8ecc9", "#2e8b3a", ",bold"),
    "goal": ("#7bc47f", "#1f6b29", ",bold"),
}
KIND_ICON = {"start": "🟦", "expand": "🔶", "push": "➕", "duplicate": "✂️", "worse": "✂️",
             "stale": "♻️", "limit": "⛔", "goal": "🎯", "exhausted": "❌"}
PLAY_SECONDS = 0.6


def tree_dot(trace: SearchTrace, step: int, show_skipped: bool) -> str:
    """Graphviz DOT for the search tree as it looked after `step` events."""
    status = statuses_at(trace, step)
    on_path = set(trace.path) if trace.goal_node in status else set()
    lines = ["digraph T {", "rankdir=LR; bgcolor=transparent; nodesep=0.15; ranksep=0.35;",
             'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=9];',
             "edge [color=\"#9aa7bd\", arrowsize=0.5];"]
    shown = {n for n, s in status.items()
             if show_skipped or s not in ("skipped", "stale", "limit")}
    for node_id in sorted(shown):
        node = trace.nodes[node_id]
        fill, border, extra = STYLE[status[node_id]]
        title = node_title(node, trace.start_term)
        term, _, courses = title.partition(" +")
        label = f"#{node_id} {term}"
        codes = courses.split()
        for i in range(0, len(codes), 3):
            label += "\\n" + ("+" if i == 0 else " ") + " ".join(codes[i:i + 3])
        label += f"\\ng={node.g:.2f}"
        if trace.algorithm == "astar" and node.h is not None:
            label += f"  h={node.h:.2f}  f={node.g + node.h:.2f}"
        lines.append(f'n{node_id} [label="{label}", fillcolor="{fill}", color="{border}", '
                     f'style="rounded,filled{extra}"];')
    for node_id in sorted(shown):
        parent = trace.nodes[node_id].parent
        if parent is not None and parent in shown:
            bold = node_id in on_path and parent in on_path
            attrs = ' [color="#2e8b3a", penwidth=2.2]' if bold else ""
            lines.append(f"n{parent} -> n{node_id}{attrs};")
    lines.append("}")
    return "\n".join(lines)


def _controls(last: int) -> None:
    def move(delta: int | None = None, to: int | None = None) -> None:
        st.session_state.watch_playing = False
        current = st.session_state.watch_step
        st.session_state.watch_step = max(0, min(last, to if to is not None
                                                 else current + (delta or 0)))

    def toggle_play() -> None:
        if st.session_state.watch_step >= last:
            st.session_state.watch_step = 0
        st.session_state.watch_playing = not st.session_state.watch_playing

    cols = st.columns(5)
    cols[0].button("⏮ Reset", width="stretch", on_click=move, kwargs={"to": 0})
    cols[1].button("◀ Back", width="stretch", on_click=move, kwargs={"delta": -1})
    cols[2].button("Step ▶", type="primary", width="stretch", on_click=move,
                   kwargs={"delta": 1})
    cols[3].button("⏸ Pause" if st.session_state.watch_playing else "▶ Play",
                   width="stretch", on_click=toggle_play)
    cols[4].button("⏭ Run to end", width="stretch", on_click=move, kwargs={"to": last})


def _viewer(trace: SearchTrace, other_expanded: dict[str, int]) -> None:
    last = len(trace.events) - 1
    if st.session_state.watch_playing:
        if st.session_state.watch_step < last:
            st.session_state.watch_step += 1
        else:
            st.session_state.watch_playing = False
            st.rerun(scope="app")
    step = st.session_state.watch_step
    event = trace.events[step]
    done = trace.events[: step + 1]

    cols = st.columns(4)
    cols[0].metric("Step", f"{step + 1} / {last + 1}")
    cols[1].metric("Expanded", sum(e.kind == "expand" for e in done))
    cols[2].metric("Frontier", event.frontier, help="States generated but not yet expanded.")
    cols[3].metric("Explored", event.closed, help="States already expanded (closed set).")
    (st.success if event.kind == "goal" else st.info)(
        f"{KIND_ICON[event.kind]} **{event.kind.upper()}** · {event.text}")

    tree, log = st.columns([3, 2], gap="medium")
    with tree:
        show_skipped = st.toggle("Show skipped branches", value=True, key="watch_skipped")
        st.graphviz_chart(tree_dot(trace, step, show_skipped), width="stretch")
        st.caption("🟧 being expanded · 🟦 expanded · ⬜ frontier (waiting) · "
                   "dashed = skipped (duplicate or worse path) · 🟩 solution path")
    with log:
        st.markdown("**Process log**")
        recent = done[-12:]
        st.markdown("\n".join(
            f"{'**' if e.step == step else ''}`{e.step + 1:>3}` {KIND_ICON[e.kind]} "
            f"{e.text}{'**' if e.step == step else ''}" for e in reversed(recent)))
    if step == last and trace.goal_node is not None:
        name = ALGORITHM_NAMES[trace.algorithm]
        expanded = trace.result.stats["expanded"]
        others = ", ".join(f"{ALGORITHM_NAMES[a]} {n}" for a, n in other_expanded.items()
                           if a != trace.algorithm)
        st.success(f"{name} found a {len(trace.result.semesters)}-term plan (cost "
                   f"{trace.result.stats['cost']:g}) after expanding {expanded} states. "
                   f"Same scenario with the other algorithms: {others} expanded.")


def render_search_view(get_trace: Callable[[str], SearchTrace], default_algorithm: str,
                       signature: tuple) -> None:
    """The whole tab. `get_trace(algorithm)` returns the (cached) trace for the shown plan."""
    st.session_state.setdefault("watch_algo", default_algorithm)
    algorithm = st.segmented_control("Algorithm to watch", ALGORITHMS, key="watch_algo",
                                      format_func=ALGORITHM_NAMES.__getitem__,
                                      required=True)
    st.caption(ALGORITHM_IDEAS[algorithm])
    trace = get_trace(algorithm)
    if st.session_state.get("watch_sig") != (signature, algorithm):
        st.session_state.watch_sig = (signature, algorithm)
        st.session_state.watch_step = 0
        st.session_state.watch_playing = False
    if trace.truncated:
        st.warning("This search is very large; only the first events are shown.")
    _controls(len(trace.events) - 1)
    other = {a: get_trace(a).result.stats["expanded"] for a in ALGORITHMS}
    run_every = PLAY_SECONDS if st.session_state.watch_playing else None
    st.fragment(_viewer, run_every=run_every)(trace, other)
