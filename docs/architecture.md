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
    explain.py           log summariser                 [milestone 8]
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

### Search (`reasoning/search.py`) — planned

- State key: `(completed, current_term)`.
- Successors: eligible ∧ relevant courses → `valid_combos` → next state per bundle.
- Costs: BFS 1/term; UCS and A* `1 + 0.05·credits`/term (D1).
- Heuristic: `max(ceil(remaining_required_credits / max_credits), longest_remaining_chain)`
  — both lower bounds on terms left, and each term costs ≥ 1, so admissible.
- Limit: 16 terms, else `INFEASIBLE`.
