# Architecture

```text
courseplanner/
  app.py                 Streamlit UI (5 tabs)          [milestones 9-10]
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
