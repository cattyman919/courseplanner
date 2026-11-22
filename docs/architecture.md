# Architecture

```text
courseplanner/
  app.py                 Streamlit UI: mode switch, AI planner sidebar + 6 tabs
  domain/
    models.py            frozen dataclasses: Course, StudentProfile, PlanState,
                         RuleResult, PlanResult
    catalog.py           CATALOG: 25 courses (source of truth for seeding)
    profiles.py          PROFILES: 3 demo students
  db/
    schema.sql           9 tables, PRAGMA user_version = 1
    connection.py        get_connection(), init_db()  (idempotent create + seed)
    seed.py              seed_if_empty(): one transaction, executemany
    repo.py              load/save functions, no business logic
  reasoning/
    rules.py             production rules -> RuleResult
    combos.py            pruned DFS bundle generator
    search.py            BFS / UCS / A*                 [milestones 6-7]
    explain.py           rule-log builder + summariser
    trace.py             event recording for step-by-step replay
    advisor.py           rule checks for student-chosen terms
  ui/
    builder.py           "Build my plan" mode
    search_view.py       "Watch the Search" tab
  tests/                 pytest, one file per layer
  docs/                  these notes
```

## Data flow

```text
domain/catalog.py, profiles.py
        │  seed_if_empty (first launch only)
        ▼
  courseplanner.db  ──load_catalog / load_profiles──►  dict[str, Course], StudentProfile
        ▲                                                   │
        │ save_plan / list / load / delete                  ▼
        │                                      reasoning: rules → combos → search
        │                                                   │
        └────────────────────  PlanResult  ◄────────────────┘
                                   │
                                   ▼
                              app.py tabs
```

SQLite is the persistence layer; the reasoning engine only ever sees in-memory dataclasses.
The app loads the catalog and profiles once and caches them.

## Database

| Table | Purpose |
|---|---|
| `courses` | code, title, credits (CHECK 1–6), category, track |
| `course_prereqs`, `course_coreqs` | course → required course edges |
| `course_slots` | course → meeting slot strings |
| `course_offerings` | course → `fall` / `spring` (CHECK) |
| `profiles`, `profile_completed` | demo students and their completed sets |
| `saved_plans` | one row per saved plan; `plan_json` holds semesters, start term, completed set, stats |
| `rule_log` | one row per RuleResult of a saved plan; `ON DELETE CASCADE` from `saved_plans` |

- `PRAGMA foreign_keys = ON` per connection; `check_same_thread=False` for Streamlit.
- `init_db()` raises a clear error on schema-version mismatch: delete the DB file to reset.
- Join-table rows are read back in insertion order (`ORDER BY rowid`) so a `Course`
  round-trips exactly.
- All SQL is parameterised; multi-row writes run inside `with conn:`.

## Streamlit app (`app.py`)

| Part | Behaviour |
|---|---|
| Caching | `@st.cache_resource` DB connection (runs `init_db()` once); `@st.cache_data(ttl=600)` catalog and profiles; `@st.cache_data` `plan_for(profile, track, max_credits, algorithm, start_term)` |
| Sidebar | scenario, target track (defaults to the profile's, reset per scenario), max credits 12–21, algorithm (default A\*), "Run all three algorithms" (default on), **Generate plan**, **Save plan** (disabled until a plan exists) |
| Session state | `plan`, `profile_name`, `algorithm`, plus `params` (inputs behind the shown plan), `comparison`, `confirm_delete`, `flash` (one-shot success message) |
| Semester Plan | summary from `summarize`, one column per term (wraps every 4), course cards with code, title, credits, slots; red `missing prereq` badge from `inserted_prereqs`; total terms/credits footer; `st.error` + pruned list when infeasible |
| Rule & Inference Log | `#`, Rule, Subject, OK, Detail; Rule multiselect and OK filter; "Show only pruned courses" expander |
| Search Stats | expanded / generated / ms / cost metrics; comparison table across BFS, UCS, A\* |
| Saved Plans | `list_saved_plans` table (never cached), single-row selection → preview (terms, credits, cost, log size); **Load** restores the plan, the sidebar widgets, and jumps to Semester Plan; **Delete** asks for confirmation, then `delete_saved_plan` + rerun |
| Prerequisite Graph | DOT via `st.graphviz_chart`; a "Current term" slider recolours nodes: green completed (before that term), yellow that term, blue planned later, grey unmet; dashed = not required for the track |

The plan only changes when **Generate plan** is pressed; if sidebar inputs differ from the
shown plan, a caption says so.

**Callbacks, not `if st.button(...)`:** Generate, Save, and Load run as `on_click`
callbacks, which Streamlit executes *before* the script. That way the page — including the
sidebar's Save button, drawn above the main area — already sees the new plan on the same
run. (With an inline `if st.button` the Save button stayed disabled for one run after
generating.) Sidebar widgets are keyed (`scenario`, `track_<profile>`, `max_credits`,
`algo`, `compare`) and seeded with `setdefault`, so Load can set them; tabs use
`key="tab", on_change="rerun"` so Load can switch to the plan tab.

**Saving:** the plan on screen is saved with the inputs that produced it (`params`), not
the current sidebar values. A loaded plan has no comparison table; regenerate for one.

## Reasoning pipeline

### Rules (`reasoning/rules.py`)

| Function | Rule(s) | Notes |
|---|---|---|
| `check_eligibility` | `PREREQ` → `OFFERING` → `OK` | OK detail shows the chain, e.g. `Completed(CS201) ∧ Completed(MATH210) ⇒ Eligible` |
| `check_schedule` | `CREDIT_CAP`, `CONFLICT` | returns *all* violations; empty list = valid |
| `required_courses_for` | — | math + core + target track, closed under prereqs |
| `goal_reached` | — | required ⊆ completed and elective credits ≥ target |
| `check_relevance` / `is_relevant` | `PRUNED` / `OK` | "already completed", "not needed for track X", "elective credits already satisfied" |
| `term_of` | — | term name from start term + index |

### Combos (`reasoning/combos.py`)

`valid_combos(eligible, max_credits, min_credits=9, elective_credits_needed=None)`:
sorted by code, DFS take-before-skip, prune on cap/slot clash, emit maximal bundles only,
below-minimum fallback, cap 64 with a `truncated` flag. See [decisions.md](decisions.md) D3.

### Search (`reasoning/search.py`)

| Piece | Behaviour |
|---|---|
| `state_key` | `(completed, current_term)` — the term name, not just index parity |
| `candidates` | courses that pass `check_relevance` and `check_eligibility`, sorted by code |
| `successors` | one next state per bundle from `valid_combos`; if no bundle exists, a single "wait a term" successor |
| `edge_cost` | BFS `1`; UCS (and A*) `1 + 0.05·credits` (D1) |
| `run_plan` | one best-first driver: FIFO queue for BFS, heap with insertion counter for UCS (deterministic ties); closed set on state key; goal test on pop |
| `explain_plan` | lives in `explain.py`; replays the chosen plan and builds the rule log (D2) |

- **Limit:** states at term 16 are not expanded; exhausting the frontier returns
  `semesters=[]`, the start-state prunes, and an `INFEASIBLE` entry.
- **Stats:** `expanded` (states whose successors were generated), `generated` (successor
  edges), `ms` (`time.perf_counter`), `cost` (path cost of the returned plan).

### A\* heuristic

```text
remaining     = required_courses_for(profile) - completed
elective_need = max(0, electives_required - elective_credits(completed))
credit_need   = credits(remaining) + elective_need
h = max(ceil(credit_need / max_credits), longest_prereq_chain(remaining)) + 0.05 · credit_need
```

- **Admissible:** at least `max(...)` terms remain (credits per term are capped, and each
  link of an open prerequisite chain needs its own term). Each term costs ≥ 1, and each
  still-needed credit is charged 0.05 exactly once when taken, so `h` ≤ the true remaining cost.
- **Consistent:** one term lowers each bound by at most 1 and `credit_need` by at most the
  credits taken `c`, so `h(n) − h(n') ≤ 1 + 0.05·c`, the edge cost. The closed set therefore
  never discards a cheaper path.
- `h = 0` at any goal state.

### Explanation (`reasoning/explain.py`)

| Function | Purpose |
|---|---|
| `explain_plan` | builds the chronological rule log for a plan (format below) |
| `combo_label` | `"Fall 2026: CS301, CS310, MATH301"` |
| `missing_prereqs` | course codes named in any `PREREQ` detail |
| `inserted_prereqs` | planned catch-up courses for the red UI badge (D6) |
| `top_pruned` | courses held back most often (`PRUNED`, `PREREQ`, `OFFERING`) |
| `summarize` | markdown: terms, credits, algorithm, cost, effort, top-3 held-back courses |

### Rule log format

Per plan term, in order:
1. `PRUNED` for courses not needed (each course/reason logged once, the first term it applies).
2. `PREREQ` / `OFFERING` / `OK` for every needed, not-yet-completed course, detail prefixed
   with the term label (e.g. `Spring 2027: missing prerequisite(s): CS201, MATH210`).
3. `CONFLICT` for each pair of eligible courses sharing a slot (`cannot take both`).
4. One `OK` row whose subject is the term label, listing the bundle taken and its credits.

### Measured results

States expanded (A\* cost equals UCS cost in every case):

| Profile | Terms | Cost | 18 cr: BFS / UCS / A\* | 15 cr: BFS / UCS / A\* | 12 cr: BFS / UCS / A\* |
|---|---|---|---|---|---|
| On-track | 3 | 4.45 | 14 / 15 / **4** | 28 / 33 / **12** | 58 / 69 / **26** |
| Transfer | 4 | 5.95 | 8 / 8 / **4** | 8 / 8 / **4** | 24 / 29 / **9** |
| Heavy electives | 2 | 3.05 | 6 / 6 / **2** | 13 / 17 / **8** | 17 / 22 / **9** |

Every run takes under 4 ms. Lowering the cap does not lengthen any plan; it enlarges the
search, which is where A\*'s advantage shows most.

## Interactive modes

Inspired by the course's SearchLab example (tic-tac-toe with a visible game tree): the
student acts, the AI responds, and the AI's reasoning is visible step by step.

### Search trace (`reasoning/trace.py`)

`run_plan(..., observer=fn)` calls `fn(kind, data)` at every search event; with no
observer the search is unchanged. Every node gets an integer id (start = 0).

| Event | Meaning |
|---|---|
| `start` | start state pushed onto the frontier |
| `expand` | state popped and expanded; lists the eligible, needed courses |
| `push` | successor generated and added to the frontier (g, h recorded) |
| `duplicate` | successor reaches an already-expanded state, so it is skipped |
| `worse` | successor reaches a queued state that already has a lower-or-equal g, so it is skipped |
| `stale` | popped entry whose state was already expanded via a cheaper path |
| `limit` | 16-term limit reached; not expanded |
| `goal` | goal test passes; the plan is the parent chain to this node |
| `exhausted` | frontier empty: infeasible |

`trace_search` turns these into `TraceEvent`s (with plain-English text) and `TraceNode`s.
`statuses_at(trace, k)` replays the first `k+1` events, giving each visible node a status:
frontier, current, expanded, skipped, stale, limit, goal or path. Tests check that a
traced run returns exactly the same plan and expansion count as an untraced run.

### Watch the Search tab (`ui/search_view.py`)

- **Controls:** ⏮ Reset, ◀ Back, Step ▶, ▶ Play / ⏸ Pause, ⏭ Run to end. Play uses
  `st.fragment(run_every=0.6)`, so only the viewer reruns while playing.
- **Shown at each step:**
  - metrics: step, expanded so far, frontier size, explored (closed) size
  - the current event, highlighted
  - the 12 most recent events as a process log
  - the tree as Graphviz DOT, left to right. Node labels give id, term, courses and g,
    plus h and f for A\*.
- **At the end:** the solution path is drawn in green, and the number of states each
  algorithm expanded is compared.
- **Reset:** changing the algorithm or regenerating the plan resets the replay.

### Build my plan (`reasoning/advisor.py`, `ui/builder.py`)

| Piece | Behaviour |
|---|---|
| Setup | start from a preset or a blank student; edit completed courses, track, first term, elective credits required, max credits. Locked once a term is committed (Start over unlocks it). |
| `course_verdict` | PREREQ / OFFERING first (blocking, 🔒), then relevance: PRUNED is advisory (⚠️, allowed), OK is ✅ |
| `check_term` | per-course verdicts plus `check_schedule` (CONFLICT, CREDIT_CAP); `can_commit` iff at least one pick and no blocking rule |
| `available_now` | what the planner itself would consider (eligible ∧ needed) |
| `suggest_rest` | `run_plan` from the student's current state (start term shifted to the current term) |
| Picker | every not-yet-completed course, grouped Required / Electives / Other, with an icon and a short reason (e.g. "needs CS301") |
| AI help | **Pick this term for me** ticks the first term of the optimal plan; **Plan the rest for me** shows the remaining plan with **Accept** |
| Progress | committed-term timeline, required courses left, elective credits, success message at the goal |

Checkbox state is keyed `pick_<term>_<code>`, so **Undo last term** brings that term's
picks back.
