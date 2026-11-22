"""'Build my plan' mode: the student picks courses term by term, the rule engine checks
every pick, and the AI can pick a term or plan the rest from wherever the student is."""

import streamlit as st

from domain.models import Course, PlanResult, RuleResult, StudentProfile
from reasoning.advisor import (
    available_now,
    check_term,
    course_verdict,
    progress,
    state_after,
    suggest_rest,
)
from reasoning.explain import ALGORITHM_NAMES
from reasoning.rules import MISSING_PREFIX, required_courses_for, term_label

BLANK = "Blank student (choose your own completed courses)"
TRACKS = ("ai", "systems", "theory")
ICON = {"OK": "✅", "PRUNED": "⚠️", "PREREQ": "🔒", "OFFERING": "🔒", "CONFLICT": "❌",
        "CREDIT_CAP": "❌"}


# --- state ------------------------------------------------------------------------------

def _reset(profiles: dict[str, StudentProfile]) -> None:
    """Callback: start the builder from the chosen preset (or a blank student)."""
    base = profiles.get(st.session_state.bld_base)
    st.session_state.bld_completed = sorted(base.completed) if base else []
    st.session_state.bld_track = base.target_track if base else "ai"
    st.session_state.bld_start = base.start_term if base else "fall"
    st.session_state.bld_electives = base.elective_credits_required if base else 9
    st.session_state.bld_terms = []
    st.session_state.bld_suggestion = None
    for key in [k for k in st.session_state if str(k).startswith("pick_")]:
        del st.session_state[key]


def _student() -> StudentProfile:
    """The student being planned, built from the setup widgets."""
    return StudentProfile(
        name="You", completed=frozenset(st.session_state.bld_completed),
        target_track=st.session_state.bld_track, max_credits=st.session_state.bld_cap,
        start_term=st.session_state.bld_start,
        elective_credits_required=st.session_state.bld_electives)


def _picks(term_index: int, catalog: dict[str, Course]) -> list[str]:
    """Course codes currently ticked for the given term."""
    return [c for c in sorted(catalog) if st.session_state.get(f"pick_{term_index}_{c}")]


def _set_picks(term_index: int, codes: set[str], catalog: dict[str, Course]) -> None:
    for code in catalog:
        st.session_state[f"pick_{term_index}_{code}"] = code in codes


# --- callbacks ----------------------------------------------------------------------------

def _commit(catalog: dict[str, Course]) -> None:
    index = len(st.session_state.bld_terms)
    st.session_state.bld_terms = [*st.session_state.bld_terms, _picks(index, catalog)]
    st.session_state.bld_suggestion = None


def _skip() -> None:
    st.session_state.bld_terms = [*st.session_state.bld_terms, []]
    st.session_state.bld_suggestion = None


def _undo() -> None:
    st.session_state.bld_terms = st.session_state.bld_terms[:-1]
    st.session_state.bld_suggestion = None


def _suggest(catalog: dict[str, Course]) -> PlanResult:
    student = _student()
    state = state_after(student, st.session_state.bld_terms)
    return suggest_rest(state, student, catalog, student.max_credits,
                        st.session_state.bld_algo)


def _ai_pick_term(catalog: dict[str, Course]) -> None:
    suggestion = _suggest(catalog)
    first = {c.code for c in suggestion.semesters[0]} if suggestion.semesters else set()
    _set_picks(len(st.session_state.bld_terms), first, catalog)
    st.session_state.bld_suggestion = None


def _ai_plan_rest(catalog: dict[str, Course]) -> None:
    st.session_state.bld_suggestion = _suggest(catalog)


def _accept_rest() -> None:
    suggestion: PlanResult = st.session_state.bld_suggestion
    st.session_state.bld_terms = [*st.session_state.bld_terms,
                                  *([c.code for c in t] for t in suggestion.semesters)]
    st.session_state.bld_suggestion = None


# --- view ---------------------------------------------------------------------------------

def _short_reason(result: RuleResult) -> str:
    if result.rule == "PREREQ":
        return "needs " + result.detail.split(MISSING_PREFIX, 1)[-1]
    if result.rule == "OK":
        return "eligible now"
    return result.detail


def _setup(profiles: dict[str, StudentProfile], catalog: dict[str, Course]) -> None:
    locked = bool(st.session_state.bld_terms)
    with st.expander("1 · Who are you?", expanded=not locked):
        if locked:
            st.caption("Setup is locked while you have committed terms. "
                       "Press **Start over** to change it.")
        st.selectbox("Start from", [*profiles, BLANK], key="bld_base", disabled=locked,
                     on_change=_reset, args=(profiles,))
        st.multiselect("Courses you have completed", sorted(catalog), key="bld_completed",
                       disabled=locked,
                       format_func=lambda c: f"{c} · {catalog[c].title}")
        a, b, c, d = st.columns(4)
        a.selectbox("Target track", TRACKS, key="bld_track", disabled=locked)
        b.radio("First term", ("fall", "spring"), key="bld_start", horizontal=True,
                disabled=locked, format_func=str.title)
        c.number_input("Elective credits required", 0, 21, step=3, key="bld_electives",
                       disabled=locked)
        d.slider("Max credits per term", 12, 21, key="bld_cap")


def _picker(student: StudentProfile, catalog: dict[str, Course], index: int) -> None:
    state = state_after(student, st.session_state.bld_terms)
    required = required_courses_for(student, catalog)
    groups = {"Required for your track": [], "Electives": [], "Other courses": []}
    for code, course in sorted(catalog.items()):
        if code in state.completed:
            continue
        group = ("Required for your track" if code in required
                 else "Electives" if course.category == "elective" else "Other courses")
        groups[group].append(course)
    for title, courses in groups.items():
        if not courses:
            continue
        st.markdown(f"**{title}**")
        for course in courses:
            verdict = course_verdict(course, state, student, catalog)
            st.checkbox(
                f"{ICON[verdict.rule]} **{course.code}** {course.title} · {course.credits} cr"
                f" — _{_short_reason(verdict)}_",
                key=f"pick_{index}_{course.code}",
                help=f"{verdict.rule}: {verdict.detail}. Slots: {', '.join(course.slots)}")


def _checks(student: StudentProfile, catalog: dict[str, Course], index: int) -> None:
    state = state_after(student, st.session_state.bld_terms)
    picks = _picks(index, catalog)
    check = check_term(picks, state, student, catalog, student.max_credits)
    st.markdown("**Rule check**")
    if not picks:
        st.caption("Tick courses on the left. Every pick is checked against the rules.")
    for code, result in check.per_course.items():
        line = f"{ICON[result.rule]} `{result.rule}` **{code}**: {result.detail}"
        (st.error if result.rule in ("PREREQ", "OFFERING")
         else st.warning if result.rule == "PRUNED" else st.success)(line)
    for result in check.schedule:
        st.error(f"❌ `{result.rule}` **{result.subject}**: {result.detail}")
    st.progress(min(check.credits / student.max_credits, 1.0),
                text=f"{check.credits} / {student.max_credits} credits")
    can_take = [c.code for c in available_now(state, student, catalog)]
    st.caption("You can take now (eligible and needed): "
               + (", ".join(can_take) if can_take else "nothing this term"))

    st.button("Commit this term", type="primary", width="stretch",
              disabled=not check.can_commit, on_click=_commit, args=(catalog,),
              help="Allowed when no PREREQ, OFFERING, CONFLICT, or CREDIT_CAP rule fails.")
    if not can_take:
        st.button("Skip this term (nothing to take)", width="stretch", on_click=_skip)
    st.divider()
    st.markdown("**Ask the AI**")
    st.radio("Algorithm", ("astar", "ucs", "bfs"), key="bld_algo", horizontal=True,
             format_func=ALGORITHM_NAMES.__getitem__)
    left, right = st.columns(2)
    left.button("🤖 Pick this term for me", width="stretch", on_click=_ai_pick_term,
                args=(catalog,), help="Ticks the first term of the AI's optimal plan.")
    right.button("🤖 Plan the rest for me", width="stretch", on_click=_ai_plan_rest,
                 args=(catalog,), help="Searches from your current state to graduation.")


def _suggestion(student: StudentProfile) -> None:
    suggestion: PlanResult | None = st.session_state.bld_suggestion
    if suggestion is None:
        return
    offset = len(st.session_state.bld_terms)
    name = ALGORITHM_NAMES[suggestion.algorithm]
    if not suggestion.semesters:
        st.error(f"{name} found no plan from here: "
                 + next((r.detail for r in suggestion.log if r.rule == "INFEASIBLE"),
                        "you already meet every requirement."))
        return
    with st.container(border=True):
        st.markdown(f"**🤖 {name} suggests {len(suggestion.semesters)} more term(s)** · cost "
                    f"{suggestion.stats['cost']:g} · {suggestion.stats['expanded']} states "
                    "expanded")
        cols = st.columns(min(len(suggestion.semesters), 4))
        for i, term in enumerate(suggestion.semesters):
            with cols[i % len(cols)]:
                st.markdown(f"*{term_label(student.start_term, offset + i)}*")
                st.markdown("\n".join(f"- {c.code} ({c.credits} cr)" for c in term) or "- wait")
        st.button("Accept the AI's plan", on_click=_accept_rest)


def _timeline(student: StudentProfile, catalog: dict[str, Course]) -> None:
    terms = st.session_state.bld_terms
    state = state_after(student, terms)
    status = progress(state, student, catalog)
    st.markdown("**Your plan so far**")
    if terms:
        cols = st.columns(min(len(terms), 4))
        for i, term in enumerate(terms):
            with cols[i % len(cols)].container(border=True):
                st.markdown(f"**{term_label(student.start_term, i)}**")
                st.caption(f"{sum(catalog[c].credits for c in term)} credits")
                st.markdown("\n".join(f"- {c}" for c in term) or "_(skipped)_")
    else:
        st.caption("Nothing committed yet.")
    need = max(status.elective_need, 1)
    a, b = st.columns(2)
    a.metric("Required courses left", len(status.required_left),
             help=", ".join(status.required_left) or "none")
    b.metric("Elective credits", f"{status.elective_have} / {status.elective_need}")
    st.progress(min(status.elective_have / need, 1.0) if status.elective_need else 1.0)
    if status.required_left:
        st.caption("Still required: " + ", ".join(status.required_left))
    if status.done:
        st.success(f"🎓 Every requirement for the **{student.target_track}** track is met "
                   f"after {len(terms)} term(s).")


def render_builder(profiles: dict[str, StudentProfile], catalog: dict[str, Course]) -> None:
    """The whole 'Build my plan' page."""
    if "bld_base" not in st.session_state:
        st.session_state.bld_base = next(iter(profiles))
        st.session_state.bld_cap = 18
        st.session_state.bld_algo = "astar"
        _reset(profiles)

    st.header("🧑‍🎓 Build my plan")
    st.caption("You choose the courses; the symbolic rule engine checks every choice and "
               "explains why. Ask the AI for help at any point.")
    _setup(profiles, catalog)
    student = _student()
    index = len(st.session_state.bld_terms)
    done = progress(state_after(student, st.session_state.bld_terms), student, catalog).done

    top = st.columns([4, 1])
    top[0].subheader(f"2 · Term {index + 1}: {term_label(student.start_term, index)}")
    top[1].button("Undo last term", width="stretch", on_click=_undo,
                  disabled=not st.session_state.bld_terms)
    if done:
        st.success("You're done: nothing more is required.")
    else:
        left, right = st.columns([3, 2], gap="large")
        with left:
            _picker(student, catalog, index)
        with right:
            _checks(student, catalog, index)
        _suggestion(student)
    st.divider()
    _timeline(student, catalog)
    st.button("Start over", on_click=_reset, args=(profiles,))
