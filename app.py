"""CoursePath: a symbolic course planner (Streamlit UI over SQLite + symbolic search)."""

from dataclasses import replace

import streamlit as st

from db import repo
from db.connection import get_connection, init_db
from domain.models import Course, PlanResult, StudentProfile
from reasoning.explain import ALGORITHM_NAMES, inserted_prereqs, summarize
from reasoning.rules import required_courses_for, term_label
from reasoning.search import ALGORITHMS, run_plan

TRACKS = ("ai", "systems", "theory")
RULES = ("PREREQ", "OFFERING", "CONFLICT", "CREDIT_CAP", "PRUNED", "OK", "INFEASIBLE")
TAB_NAMES = ("Semester Plan", "Rule & Inference Log", "Search Stats", "Prerequisite Graph")
COLORS = {"completed": "#7bc47f", "current": "#f5d76e", "planned": "#79a7e3", "unmet": "#d0d0d0"}

st.set_page_config(page_title="CoursePath", page_icon="🎓", layout="wide")


# --- data access (cached) -------------------------------------------------------------

@st.cache_resource
def _conn():
    init_db()
    return get_connection()


conn = _conn()


@st.cache_data(ttl=600)
def load_catalog() -> dict[str, Course]:
    """Catalog from SQLite, cached for the process."""
    return repo.load_catalog(conn)


@st.cache_data(ttl=600)
def load_profiles() -> dict[str, StudentProfile]:
    """Preset profiles from SQLite, cached for the process."""
    return repo.load_profiles(conn)


@st.cache_data(show_spinner=False)
def plan_for(profile_name: str, track: str, max_credits: int, algorithm: str,
             start_term: str) -> PlanResult:
    """Run the planner; cached on every input that can change the result."""
    profile = replace(load_profiles()[profile_name], target_track=track, start_term=start_term)
    return run_plan(profile, load_catalog(), algorithm, max_credits)


# --- session state ----------------------------------------------------------------------

st.session_state.setdefault("plan", None)          # current PlanResult
st.session_state.setdefault("profile_name", None)
st.session_state.setdefault("algorithm", None)
st.session_state.setdefault("params", None)        # inputs that produced the current plan
st.session_state.setdefault("comparison", None)    # {algorithm: PlanResult}


# --- sidebar ----------------------------------------------------------------------------

catalog = load_catalog()
profiles = load_profiles()

with st.sidebar:
    st.title("🎓 CoursePath")
    st.caption("Symbolic course planner: rules + constraint pruning + search.")
    if not profiles or not catalog:
        st.error("The catalog or profiles are empty. Run `make reset-db` and restart.")
        st.stop()
    profile_name = st.selectbox("Scenario", list(profiles))
    base = profiles[profile_name]
    track = st.selectbox("Target track", TRACKS, index=TRACKS.index(base.target_track),
                         key=f"track_{profile_name}")
    max_credits = st.slider("Max credits per term", 12, 21, base.max_credits)
    algorithm = st.radio("Algorithm", ALGORITHMS, index=ALGORITHMS.index("astar"),
                         format_func=ALGORITHM_NAMES.__getitem__, horizontal=True)
    compare = st.checkbox("Run all three algorithms", value=True,
                          help="Fills the comparison table in Search Stats.")
    generate = st.button("Generate plan", type="primary", width="stretch")

params = {"profile_name": profile_name, "track": track, "max_credits": max_credits,
          "algorithm": algorithm, "start_term": base.start_term}

if generate:
    st.session_state.plan = plan_for(**params)
    st.session_state.profile_name = profile_name
    st.session_state.algorithm = algorithm
    st.session_state.params = params
    st.session_state.comparison = (
        {a: plan_for(**{**params, "algorithm": a}) for a in ALGORITHMS} if compare else None)

plan: PlanResult | None = st.session_state.plan
shown = st.session_state.params

if plan is None:
    st.info("Pick a scenario in the sidebar and press **Generate plan**.")
    st.stop()

if shown != params:
    st.caption("ℹ️ Sidebar settings changed — press **Generate plan** to replan.")

profile = replace(profiles[shown["profile_name"]], target_track=shown["track"],
                  start_term=shown["start_term"])

tab_plan, tab_log, tab_stats, tab_graph = st.tabs(TAB_NAMES, key="tab")


# --- tab 1: semester plan ---------------------------------------------------------------

def render_plan(result: PlanResult, student: StudentProfile) -> None:
    """Timeline of terms with one card per course."""
    if not result.semesters:
        reason = next((r.detail for r in result.log if r.rule == "INFEASIBLE"), None)
        if reason is None:
            st.success("This student already meets every requirement for the track.")
            return
        st.error(f"No feasible plan: {reason}.")
        st.dataframe([{"Course": r.subject, "Reason": r.detail}
                      for r in result.log if r.rule == "PRUNED"], hide_index=True)
        return
    st.markdown(summarize(result))
    inserted = inserted_prereqs(result)
    for start in range(0, len(result.semesters), 4):
        chunk = result.semesters[start:start + 4]
        for offset, (col, term) in enumerate(zip(st.columns(4), chunk, strict=False)):
            index = start + offset
            with col:
                st.subheader(term_label(student.start_term, index))
                st.caption(f"{sum(c.credits for c in term)} credits")
                if not term:
                    st.write("_No eligible courses this term — wait._")
                for course in term:
                    with st.container(border=True):
                        st.markdown(f"**{course.code}** · {course.title}")
                        st.caption(f"{course.credits} cr · {' / '.join(course.slots)}")
                        if course.code in inserted:
                            st.badge("missing prereq", icon="⚠️", color="red",
                                     help="Catch-up course: a missing prerequisite in the log.")
    st.divider()
    total = sum(c.credits for t in result.semesters for c in t)
    left, right = st.columns(2)
    left.metric("Total terms", len(result.semesters))
    right.metric("Total credits", total)


with tab_plan:
    render_plan(plan, profile)


# --- tab 2: rule & inference log --------------------------------------------------------

with tab_log:
    rows = [{"#": i, "Rule": r.rule, "Subject": r.subject, "OK": r.ok, "Detail": r.detail}
            for i, r in enumerate(plan.log, start=1)]
    present = [r for r in RULES if any(row["Rule"] == r for row in rows)]
    left, right = st.columns([3, 1])
    chosen = left.multiselect("Rule", present, default=present)
    ok_filter = right.selectbox("OK", ("All", "True", "False"))
    filtered = [row for row in rows if row["Rule"] in chosen
                and (ok_filter == "All" or str(row["OK"]) == ok_filter)]
    st.dataframe(filtered, hide_index=True, width="stretch")
    st.caption(f"{len(filtered)} of {len(rows)} entries.")
    with st.expander("Show only pruned courses"):
        st.dataframe([row for row in rows if row["Rule"] == "PRUNED"],
                     hide_index=True, width="stretch")


# --- tab 3: search stats ----------------------------------------------------------------

with tab_stats:
    stats = plan.stats
    cols = st.columns(4)
    cols[0].metric("Expanded", stats["expanded"])
    cols[1].metric("Generated", stats["generated"])
    cols[2].metric("Elapsed (ms)", f"{stats['ms']:.2f}")
    cols[3].metric("Cost", f"{stats['cost']:g}")
    comparison = st.session_state.comparison
    if comparison:
        st.subheader("Algorithm comparison")
        st.dataframe([
            {"Algorithm": ALGORITHM_NAMES[a], "Terms": len(r.semesters),
             "Expanded": r.stats["expanded"], "Generated": r.stats["generated"],
             "Cost": r.stats["cost"], "Elapsed (ms)": r.stats["ms"]}
            for a, r in comparison.items()
        ], hide_index=True, width="stretch")
        st.caption("A\\* reaches the same cost as UCS with fewer expansions. BFS minimises "
                   "terms only, so its cost is the term count. Times are from the first "
                   "(uncached) run.")
    else:
        st.caption("Tick **Run all three algorithms** and regenerate to compare BFS, UCS, A\\*.")


# --- tab 4: prerequisite graph ----------------------------------------------------------

def prereq_dot(result: PlanResult, student: StudentProfile, cat: dict[str, Course],
               current: int) -> str:
    """Graphviz DOT for the prerequisite DAG, coloured relative to term `current`."""
    status = {code: "unmet" for code in cat}
    status.update({code: "completed" for code in student.completed})
    for index, term in enumerate(result.semesters):
        for course in term:
            status[course.code] = ("completed" if index < current
                                   else "current" if index == current else "planned")
    required = required_courses_for(student, cat)
    lines = ["digraph G {", "rankdir=LR; bgcolor=transparent;",
             'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10];']
    for code, course in sorted(cat.items()):
        dashed = "" if code in required or course.category == "elective" else ',dashed'
        lines.append(f'"{code}" [fillcolor="{COLORS[status[code]]}", '
                     f'style="rounded,filled{dashed}", tooltip="{course.title}"];')
    for code, course in sorted(cat.items()):
        lines.extend(f'"{p}" -> "{code}";' for p in course.prereqs)
    lines.append("}")
    return "\n".join(lines)


with tab_graph:
    if len(plan.semesters) > 1:
        labels = [term_label(profile.start_term, i) for i in range(len(plan.semesters))]
        current = st.select_slider("Current term", options=range(len(labels)),
                                   format_func=labels.__getitem__)
    else:
        current = 0
    st.graphviz_chart(prereq_dot(plan, profile, catalog, current), width="stretch")
    st.caption("🟩 completed · 🟨 current term · 🟦 planned later · ⬜ unmet. "
               "Dashed: not required for the target track.")
