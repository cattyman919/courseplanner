"""CoursePath: a symbolic course planner (Streamlit UI over SQLite + symbolic search)."""

from dataclasses import replace

import streamlit as st

from db import repo
from db.connection import get_connection, init_db
from domain.models import Course, PlanResult, RuleResult, StudentProfile
from reasoning.explain import ALGORITHM_NAMES, inserted_prereqs, summarize
from reasoning.rules import required_courses_for, term_label
from reasoning.search import ALGORITHMS, run_plan

TRACKS = ("ai", "systems", "theory")
RULES = ("PREREQ", "OFFERING", "CONFLICT", "CREDIT_CAP", "PRUNED", "OK", "INFEASIBLE")
TAB_NAMES = ("Semester Plan", "Rule & Inference Log", "Search Stats", "Prerequisite Graph",
             "Saved Plans")
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
st.session_state.setdefault("confirm_delete", None)  # saved-plan id awaiting confirmation
st.session_state.setdefault("flash", None)          # one-shot success message


def plan_from_saved(saved: dict, cat: dict[str, Course]) -> PlanResult:
    """Rebuild a PlanResult from `repo.load_saved_plan` output."""
    meta = saved["meta"]
    return PlanResult(
        semesters=[[cat[code] for code in term if code in cat] for term in saved["semesters"]],
        log=[RuleResult(r["subject"], bool(r["ok"]), r["rule"], r["detail"] or "")
             for r in saved["log"]],
        stats=meta.get("stats") or {"expanded": meta["expanded"], "generated": 0,
                                    "ms": meta["elapsed_ms"], "cost": meta["cost"]},
        algorithm=meta["algorithm"],
    )


def load_saved(plan_id: int) -> None:
    """Callback: restore a saved plan into session state and jump to the plan tab."""
    saved = repo.load_saved_plan(conn, plan_id)
    meta = saved["meta"]
    restored = {"profile_name": meta["profile_name"], "track": meta["target_track"],
                "max_credits": meta["max_credits"], "algorithm": meta["algorithm"],
                "start_term": meta.get("start_term", "fall")}
    st.session_state.plan = plan_from_saved(saved, load_catalog())
    st.session_state.profile_name = restored["profile_name"]
    st.session_state.algorithm = restored["algorithm"]
    st.session_state.params = restored
    st.session_state.comparison = None
    st.session_state.scenario = restored["profile_name"]
    st.session_state[f"track_{restored['profile_name']}"] = restored["track"]
    st.session_state.max_credits = restored["max_credits"]
    st.session_state.algo = restored["algorithm"]
    st.session_state.tab = TAB_NAMES[0]
    st.session_state.flash = f"Loaded saved plan #{plan_id}."


def sidebar_params() -> dict:
    """Planner inputs as currently set in the sidebar widgets."""
    name = st.session_state.scenario
    student = load_profiles()[name]
    return {"profile_name": name,
            "track": st.session_state.get(f"track_{name}", student.target_track),
            "max_credits": st.session_state.max_credits, "algorithm": st.session_state.algo,
            "start_term": student.start_term}


def generate_plan() -> None:
    """Callback: plan with the sidebar inputs (runs before the script, so the page and the
    Save button see the new plan on this same run)."""
    params = sidebar_params()
    st.session_state.plan = plan_for(**params)
    st.session_state.profile_name = params["profile_name"]
    st.session_state.algorithm = params["algorithm"]
    st.session_state.params = params
    st.session_state.comparison = (
        {a: plan_for(**{**params, "algorithm": a}) for a in ALGORITHMS}
        if st.session_state.compare else None)


def save_current() -> None:
    """Callback: persist the plan currently on screen."""
    shown = st.session_state.params
    student = replace(load_profiles()[shown["profile_name"]], target_track=shown["track"],
                      start_term=shown["start_term"])
    plan_id = repo.save_plan(conn, student, shown["algorithm"], shown["max_credits"],
                             st.session_state.plan)
    st.session_state.flash = f"Saved plan #{plan_id}. See the Saved Plans tab."


# --- sidebar ----------------------------------------------------------------------------

catalog = load_catalog()
profiles = load_profiles()

with st.sidebar:
    st.title("🎓 CoursePath")
    st.caption("Symbolic course planner: rules + constraint pruning + search.")
    if not profiles or not catalog:
        st.error("The catalog or profiles are empty. Run `make reset-db` and restart.")
        st.stop()
    st.session_state.setdefault("scenario", next(iter(profiles)))
    st.session_state.setdefault("max_credits", 18)
    st.session_state.setdefault("algo", "astar")
    profile_name = st.selectbox("Scenario", list(profiles), key="scenario")
    base = profiles[profile_name]
    st.session_state.setdefault(f"track_{profile_name}", base.target_track)
    track = st.selectbox("Target track", TRACKS, key=f"track_{profile_name}")
    max_credits = st.slider("Max credits per term", 12, 21, key="max_credits")
    algorithm = st.radio("Algorithm", ALGORITHMS, key="algo",
                         format_func=ALGORITHM_NAMES.__getitem__, horizontal=True)
    st.session_state.setdefault("compare", True)
    st.checkbox("Run all three algorithms", key="compare",
                help="Fills the comparison table in Search Stats.")
    st.button("Generate plan", type="primary", width="stretch", on_click=generate_plan)
    st.button("Save plan", width="stretch", on_click=save_current,
              disabled=st.session_state.plan is None or not st.session_state.plan.semesters,
              help="Store the plan on screen in SQLite.")

params = {"profile_name": profile_name, "track": track, "max_credits": max_credits,
          "algorithm": algorithm, "start_term": base.start_term}

plan: PlanResult | None = st.session_state.plan
shown = st.session_state.params

if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = None

if plan is not None and shown != params:
    st.caption("ℹ️ Sidebar settings changed — press **Generate plan** to replan.")

profile = (replace(profiles[shown["profile_name"]], target_track=shown["track"],
                   start_term=shown["start_term"]) if plan is not None else base)

tab_plan, tab_log, tab_stats, tab_graph, tab_saved = st.tabs(TAB_NAMES, key="tab",
                                                             on_change="rerun")
NO_PLAN = "Pick a scenario in the sidebar and press **Generate plan**."


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
    if plan is None:
        st.info(NO_PLAN)
    else:
        render_plan(plan, profile)


# --- tab 2: rule & inference log --------------------------------------------------------

def render_log(result: PlanResult) -> None:
    """Filterable table of every rule firing in the plan's log."""
    rows = [{"#": i, "Rule": r.rule, "Subject": r.subject, "OK": r.ok, "Detail": r.detail}
            for i, r in enumerate(result.log, start=1)]
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

def render_stats(result: PlanResult, comparison: dict[str, PlanResult] | None) -> None:
    """Search-effort metrics and the optional three-algorithm comparison."""
    stats = result.stats
    cols = st.columns(4)
    cols[0].metric("Expanded", stats["expanded"])
    cols[1].metric("Generated", stats["generated"])
    cols[2].metric("Elapsed (ms)", f"{stats['ms']:.2f}")
    cols[3].metric("Cost", f"{stats['cost']:g}")
    if not comparison:
        st.caption("Tick **Run all three algorithms** and regenerate to compare BFS, UCS, A\\*.")
        return
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
        dashed = "" if code in required or course.category == "elective" else ",dashed"
        lines.append(f'"{code}" [fillcolor="{COLORS[status[code]]}", '
                     f'style="rounded,filled{dashed}", tooltip="{course.title}"];')
    for code, course in sorted(cat.items()):
        lines.extend(f'"{p}" -> "{code}";' for p in course.prereqs)
    lines.append("}")
    return "\n".join(lines)


def render_graph(result: PlanResult, student: StudentProfile, cat: dict[str, Course]) -> None:
    """Prerequisite DAG with a term slider that moves the 'current term' highlight."""
    current = 0
    if len(result.semesters) > 1:
        labels = [term_label(student.start_term, i) for i in range(len(result.semesters))]
        current = st.select_slider("Current term", options=range(len(labels)),
                                   format_func=labels.__getitem__)
    st.graphviz_chart(prereq_dot(result, student, cat, current), width="stretch")
    st.caption("🟩 completed · 🟨 current term · 🟦 planned later · ⬜ unmet. "
               "Dashed: not required for the target track.")


for tab, render in ((tab_log, lambda: render_log(plan)),
                    (tab_stats, lambda: render_stats(plan, st.session_state.comparison)),
                    (tab_graph, lambda: render_graph(plan, profile, catalog))):
    with tab:
        if plan is None:
            st.info(NO_PLAN)
        else:
            render()


# --- tab 5: saved plans -----------------------------------------------------------------

def render_saved() -> None:
    """Saved-plan history from SQLite (never cached) with preview, load, and delete."""
    saved_rows = repo.list_saved_plans(conn)
    if not saved_rows:
        st.info("No saved plans yet. Generate a plan and press **Save plan** in the sidebar.")
        return
    table, preview = st.columns([3, 2])
    with table:
        event = st.dataframe(
            [{"id": r["id"], "profile": r["profile_name"], "track": r["target_track"],
              "algorithm": ALGORITHM_NAMES.get(r["algorithm"], r["algorithm"]),
              "total terms": r["total_terms"], "created_at": r["created_at"]}
             for r in saved_rows],
            hide_index=True, width="stretch", key="saved_table",
            on_select="rerun", selection_mode="single-row",
        )
    picked = event.selection.rows
    with preview:
        if not picked:
            st.caption("Select a row to preview it.")
            return
        plan_id = saved_rows[picked[0]]["id"]
        saved = repo.load_saved_plan(conn, plan_id)
        meta = saved["meta"]
        st.markdown(f"**Plan #{plan_id}** · {meta['profile_name']} · track "
                    f"`{meta['target_track']}` · "
                    f"{ALGORITHM_NAMES.get(meta['algorithm'], meta['algorithm'])} · "
                    f"{meta['max_credits']} cr/term")
        start_term = meta.get("start_term", "fall")
        for index, term in enumerate(saved["semesters"]):
            st.markdown(f"- **{term_label(start_term, index)}:** {', '.join(term) or '—'}")
        st.caption(f"{meta['total_terms']} terms · {meta['total_credits']} credits · "
                   f"cost {meta['cost']:g} · {meta['expanded']} expanded · "
                   f"{len(saved['log'])} log entries")
        load_col, delete_col = st.columns(2)
        load_col.button("Load", type="primary", width="stretch", on_click=load_saved,
                        args=(plan_id,), key=f"load_{plan_id}")
        if delete_col.button("Delete", width="stretch", key=f"delete_{plan_id}"):
            st.session_state.confirm_delete = plan_id
        if st.session_state.confirm_delete == plan_id:
            st.warning(f"Delete saved plan #{plan_id}? This cannot be undone.")
            yes, no = st.columns(2)
            if yes.button("Confirm delete", type="primary", key=f"confirm_{plan_id}"):
                repo.delete_saved_plan(conn, plan_id)
                st.session_state.confirm_delete = None
                st.session_state.flash = f"Deleted saved plan #{plan_id}."
                st.rerun()
            if no.button("Cancel", key=f"cancel_{plan_id}"):
                st.session_state.confirm_delete = None
                st.rerun()


with tab_saved:
    render_saved()
