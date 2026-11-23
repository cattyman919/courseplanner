# Architecture

```text
courseplanner/
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
  api/
    server.py            FastAPI app: JSON endpoints, serves web/ at /
    serialize.py         dataclasses -> JSON-ready dicts
  web/
    index.html           single page; views are filled in by JS
    css/style.css
    js/                  app.js router, api.js fetch wrapper, util.js DOM helpers,
                         layout.js pure layout/replay helpers, one module per view
  tests/                 pytest, one file per layer; tests/web/*.mjs for node --test
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
                     api/serialize.py → JSON → web/js views
```

SQLite is the persistence layer; the reasoning engine only ever sees in-memory dataclasses.
The API loads the catalog and profiles once at startup and caches plan and trace results
in memory (`functools.lru_cache`), keyed on every input that can change them.

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

- `PRAGMA foreign_keys = ON` per connection. The API opens a short-lived connection per
  saved-plan request, so worker threads never share one.
- `init_db()` raises a clear error on schema-version mismatch: delete the DB file to reset.
- Join-table rows are read back in insertion order (`ORDER BY rowid`) so a `Course`
  round-trips exactly.
- All SQL is parameterised; multi-row writes run inside `with conn:`.

## Web app (`api/` + `web/`)

The server is stateless and the browser holds all UI state. Each request carries
everything the engine needs, for example the builder's committed terms and current picks.
The browser never evaluates a rule. Every verdict, cost, label and search event comes from
the Python engine, so the tests on `reasoning/` also cover what the user sees.

### Endpoints (`api/server.py`)

| Endpoint | Calls | Returns |
|---|---|---|
| `GET /api/catalog`, `GET /api/profiles` | `repo.load_catalog`, `repo.load_profiles` | the knowledge base |
| `POST /api/plan` {profile, track, max_credits, algorithm, compare} | `run_plan`, `required_courses_for` | labelled terms, rule log (with parsed `missing` prereqs), stats, `inserted` catch-up courses, top-pruned, optional all-algorithm comparison |
| `POST /api/trace` {same} | `trace_search` | nodes (id, parent, depth, term, combo, g, h), events (kind, node, text, frontier, closed, and the `status` the event gives its node), solution path, expansions per algorithm |
| `POST /api/builder/check` {student, terms, picks} | `state_after`, `course_verdict`, `check_term`, `available_now`, `progress` | a verdict for every remaining course, the term check, term labels, progress |
| `POST /api/builder/suggest` {student, terms, algorithm} | `suggest_rest` | the remaining plan, labelled from the current term |
| `GET/POST /api/plans`, `GET/DELETE /api/plans/{id}` | `repo.save_plan` / `list_saved_plans` / `load_saved_plan` / `delete_saved_plan` | saved plans. Saving re-runs the plan on the server, so the browser can't store a forged plan. |

Validation uses pydantic: algorithm and track must be known values and max credits must
be 12–21. Unknown profiles or course codes get a 422. `create_app(db_path)` builds the app
against any SQLite file, and the tests use a temporary one.

### Front end (`web/`)

No framework, no build step, no CDN: ES modules served by the same FastAPI app.
`util.js` builds DOM and SVG elements and always sets text with `textContent`. `app.js`
loads the catalog and profiles, then routes on the URL hash (`#planner`, `#build`,
`#watch`, `#graph`, `#saved`). Views share a small context object with an event bus:
- `plan`: the planner shows a new plan, and the graph recolours.
- `saved`: the saved-plans list refreshes.
- `load-saved`: the planner shows a stored plan.

| View | Module | Interaction |
|---|---|---|
| AI planner | `planner.js` | Settings re-plan live, and a sequence counter drops stale responses. Terms are cards. Clicking a course opens "Why this course?" with every log row about it. The rule log has per-rule toggle chips and a text filter. A bar chart compares the three algorithms. |
| Build my plan | `builder.js` | Course cards grouped Required / Electives / Not needed. Each click POSTs to `/api/builder/check` and re-renders. Hover highlights missing prerequisites. Commit, Skip, Undo (restores that term's picks), AI pick / plan the rest / Accept. Setup collapses and locks after the first commit. |
| Watch the search | `watch.js` | Fetches one trace, then replays it entirely in the browser. Reset / Back / Step / Play with speed / Run to end, a scrubber, and ← → space Home End. On each step `layout.js` lays out only the nodes visible so far, so the tree stays compact, and nodes slide to their new positions. Follow scrolls the tree box (never the page) to the current node. Click a node for g/h/f and its path. |
| Prerequisite graph | `graph.js` | Layered DAG by prerequisite depth, coloured by the planned term. Hover or click lights up the prerequisite closure (amber) and the unlock closure (blue) and fades the rest. |
| Saved plans | `saved.js` | Table from SQLite. Load emits `load-saved`; Delete needs a second, confirming click. |

### Accessibility

A UI review against the ui-ux-pro-max guidelines on 2026-11-23 led to these rules:

- **Keyboard:** every control is a `<button>` or has `role="button"`, `tabindex="0"` and
  Enter/Space handling (`util.pressable`), which covers search-tree and graph nodes. Views
  that redraw wrap the redraw in `util.keepFocus`, which puts focus back on the same
  control (matched by `data-key`/`data-code`) or on the next heading.
- **Focus:** one global `:focus-visible` ring, a 3px accent outline. SVG nodes get a dark
  stroke instead.
- **Contrast and size:** every text colour reaches at least 4.5:1 on the backgrounds it
  sits on, and no text is smaller than 12px. Graph term colours are dark enough for their
  `T1` tags.
- **State:** toggles expose `aria-pressed`, and the current log step has
  `aria-current="step"`.
- **Screen readers:** a persistent `#announcer` live region (`util.announce`) reads out each
  builder action with the rule verdicts, each new plan's headline, manual search steps,
  the final result (but not every step during Play), and graph selections.
- **Motion:** `prefers-reduced-motion` turns off transitions and smooth scrolling.

`layout.js` has no DOM code: `replay` mirrors `reasoning.trace.statuses_at`, and
`layoutTree`, `layoutDag`, `prereqDepth` and `closure` are pure. `tests/web/test_layout.mjs`
covers them with `node --test`.

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

### Advisor rules for Build my plan (`reasoning/advisor.py`)

| Piece | Behaviour |
|---|---|
| Setup | start from a preset or a blank student; edit completed courses, track, first term, elective credits required, max credits. Locked once a term is committed (Start over unlocks it). |
| `course_verdict` | PREREQ / OFFERING first (blocking, 🔒), then relevance: PRUNED is advisory (⚠️, allowed), OK is ✅ |
| `check_term` | per-course verdicts plus `check_schedule` (CONFLICT, CREDIT_CAP); `can_commit` iff at least one pick and no blocking rule |
| `available_now` | what the planner itself would consider (eligible ∧ needed) |
| `suggest_rest` | `run_plan` from the student's current state (start term shifted to the current term) |
| `progress` | required courses left, elective credits have/need, goal reached |

The UI for these rules is described under [Front end](#front-end-web).
