# CoursePath — a symbolic course planner

CoursePath plans a CS student's remaining semesters with classical symbolic AI. It has no
machine learning and makes no LLM calls. The course catalog is a knowledge base of facts:
prerequisites, term offerings, time slots and credits. Production rules decide which
courses are eligible and which are worth taking. Constraint pruning builds each term's
valid course bundles. BFS, UCS and A\* search over semester states for a plan that meets the
student's track requirements. Every rule that fires is logged, so the app can explain
*why* each course lands where it does. It runs locally with Streamlit and SQLite.

There are two modes:

- **🤖 AI planner:** pick a student and the search plans every remaining semester. The
  **Watch the Search** tab replays that search step by step, like a debugger, showing the
  tree growing, the frontier and which branches get skipped.
- **🧑‍🎓 Build my plan:** *you* pick the courses, term by term. The rule engine checks
  every pick live (✅ eligible, 🔒 missing a prerequisite or not offered this term,
  ⚠️ not needed for your track, ❌ time clash or over your credit limit) and explains each
  verdict. At any point you can ask the AI to pick this term or plan the rest from where
  you are.

## How it maps to Symbolic AI

| Concept | Where it lives |
|---|---|
| **Knowledge representation** | Frozen dataclasses (`Course`, `StudentProfile`, `PlanState`) in `domain/models.py`. The catalog is a set of ground facts, persisted in SQLite. |
| **Production rules** | `reasoning/rules.py`: each rule is a condition ⇒ conclusion that returns a `RuleResult`. Example: `Completed(CS201) ∧ Completed(MATH210) ⇒ Eligible(CS301)` (`PREREQ`), `Offered(c, term)` (`OFFERING`), `CREDIT_CAP`, `CONFLICT`, and the relevance rule (`PRUNED`). |
| **Forward-chaining-style rule log** | `reasoning/explain.py` replays the chosen plan term by term. Facts derived in one term (newly completed courses) enable rules in the next, and each firing is recorded in order. |
| **Constraint pruning** | `reasoning/combos.py`: depth-first take/skip search that cuts any branch exceeding the credit cap or clashing on a time slot. The relevance rule also prunes courses that don't advance the goal. |
| **Heuristic search** | `reasoning/search.py`: BFS, UCS and A\* over `(completed set, term)` states. A\* uses an admissible, consistent heuristic. |
| **Watching the search** | `reasoning/trace.py` records every search event (expand, generate, skip duplicate or worse path, goal) so the **Watch the Search** tab can replay it step by step. |
| **Rule-based advising** | `reasoning/advisor.py` checks a student's own picks with the same rules and decides whether the term can be committed. The search can take over from any state the student reaches. |

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run streamlit run app.py
```

Or use the Makefile: `make run`, `make test`, `make lint` (`make` lists every target).

The SQLite database `courseplanner.db` is created and seeded automatically on first
launch. You don't need environment variables, secrets or a network service.

Run the tests with `uv run pytest -q`.

## Architecture

```text
courseplanner/
  app.py                 Streamlit UI: mode switch, AI planner sidebar + 6 tabs
  Makefile               install / run / test / lint / reset-db / clean
  domain/
    models.py            Course, StudentProfile, PlanState, RuleResult, PlanResult
    catalog.py           25-course catalog (source of truth for seeding)
    profiles.py          3 demo students
  db/
    schema.sql           9 tables, PRAGMA user_version = 1
    connection.py        get_connection(), init_db() (idempotent create + seed)
    seed.py              seed_if_empty(): one transaction
    repo.py              load / save / list / delete; no business logic
  reasoning/
    rules.py             production rules -> RuleResult
    combos.py            pruned DFS bundle generator
    search.py            BFS / UCS / A*, heuristic
    explain.py           rule-log builder + summary
    trace.py             event-by-event search recording for replay
    advisor.py           rule checks for student-chosen terms
  ui/
    builder.py           "Build my plan" mode
    search_view.py       "Watch the Search" tab (Step / Back / Play / Run to end)
  tests/                 pytest, one file per layer
  docs/                  design decisions, architecture, catalog, development notes
```

```text
domain/*.py --seed--> courseplanner.db --load--> Course / StudentProfile
                            ^                          |
                       save / load            rules -> combos -> search
                            |                          |
                            +------ PlanResult <-------+ --> app.py tabs
```

## Data model

```python
@dataclass(frozen=True)
class Course:
    code: str
    title: str
    credits: int
    prereqs: tuple[str, ...] = ()
    coreqs: tuple[str, ...] = ()
    offered: tuple[str, ...] = ("fall", "spring")
    slots: tuple[str, ...] = ()
    category: str = "core"          # "core" | "track" | "elective" | "gened" | "math"
    track: str | None = None        # "ai" | "systems" | "theory" | None

@dataclass(frozen=True)
class StudentProfile:
    name: str
    completed: frozenset[str]
    target_track: str
    max_credits: int = 18
    start_term: str = "fall"
    elective_credits_required: int = 9

@dataclass(frozen=True)
class PlanState:
    completed: frozenset[str]
    term_index: int

@dataclass(frozen=True)
class RuleResult:
    subject: str
    ok: bool
    rule: str   # "PREREQ" | "OFFERING" | "CREDIT_CAP" | "CONFLICT" | "PRUNED" | "OK" | "INFEASIBLE"
    detail: str

@dataclass
class PlanResult:
    semesters: list[list[Course]]
    log: list[RuleResult]
    stats: dict  # {"expanded": int, "generated": int, "ms": float, "cost": float}
    algorithm: str
```

To graduate in a track, a student must complete every `math` and `core` course, every
`track` course for their target track (plus those courses' prerequisites), and enough
`elective` credits. Gen-ed is never required. The full catalog and the three profiles are
in [docs/catalog.md](docs/catalog.md).

## Persistence

**Schema:**
- `courses`, plus join tables for prerequisites, corequisites, time slots and term offerings
- `profiles` and `profile_completed`
- `saved_plans`, one row per saved plan, with the semesters and stats in `plan_json`
- `rule_log`, one row per rule firing, deleted with its plan via `ON DELETE CASCADE`

All SQL is parameterised, multi-row writes run in a single transaction, and
`PRAGMA foreign_keys = ON` is set on every connection.

**Why SQLite?** The data is small, single-user and local. SQLite ships with Python, needs
no server, and gives real foreign keys and transactions. Postgres would add a service to
install for no benefit. An ORM would hide the schema, which is part of what this project
demonstrates. The engine itself works on in-memory dataclasses; SQLite is only the
persistence layer.

**Location and reset:** `courseplanner.db` lives in the project root and is ignored by git.
To reset it, run `rm courseplanner.db` (or `make reset-db`) and restart the app; it is
recreated and reseeded. If the schema version doesn't match, the app tells you to delete
the file.

## Cost models and the A\* heuristic

| Algorithm | Edge cost per term | Optimises |
|---|---|---|
| BFS | `1` | fewest terms |
| UCS | `1 + 0.05 · credits` | fewest terms, then fewest credits |
| A\* | `1 + 0.05 · credits` (same as UCS) | same as UCS, with fewer expansions |

UCS and A\* share one cost function, so UCS is A\* with `h = 0`, and the test that
"A\* cost == UCS cost" is meaningful. This is a deliberate change from the assignment
brief; see [docs/decisions.md](docs/decisions.md).

```text
credit_need = credits of remaining required courses + missing elective credits
h = max(ceil(credit_need / max_credits), longest_open_prereq_chain) + 0.05 · credit_need
```

Admissibility in three lines:
1. At most `max_credits` fit in a term, so at least `ceil(credit_need / max_credits)` terms remain.
2. Each link in an open prerequisite chain needs its own term, so the chain length is also a lower bound.
3. Each term costs at least 1, and each still-needed credit costs 0.05 once, so `h` never exceeds the true remaining cost.

The heuristic is also consistent: one term lowers `h` by at most that term's cost.

## Demo script (about 6 minutes)

Run `make run` and open http://localhost:8501. The default algorithm is A\*, and
"Run all three algorithms" is on.

1. **On-track + A\*.** Pick *On-track* and press **Generate plan**. You get a 3-term plan:
   Fall 2026 *CS301, CS310, CS350, CS360, MATH301*, Spring 2027 *AI320, AI330, CS390*,
   Fall 2027 *AI401*. That's 29 credits at cost 4.45. **Search Stats** shows A\* expanded
   4 nodes, against 14 for BFS and 15 for UCS.
2. **Transfer.** Switch to *Transfer* and regenerate. The plan grows to 4 terms (starting
   Spring 2027), and the catch-up courses CS201, MATH210 and CS210 get red
   **missing prereq** badges. In **Rule & Inference Log**, filter Rule to `PREREQ`. You'll
   see `CS301 · Spring 2027: missing prerequisite(s): CS201, MATH210`. Filter to `CONFLICT`
   to see `CS210/MATH210 · both meet MW 10:00-11:30; cannot take both`.
3. **Tighter credit cap.** Switch back to *On-track*, set **Max credits per term** to 12,
   and regenerate. The plan is still 3 terms, because the prerequisite chain sets the
   length, not credits. The course load is spread out to 10 / 10 / 9 credits, and the
   search grows a lot: A\* expands 26 nodes (142 generated), up from 4.
4. **BFS vs UCS vs A\*.** At 12 credits, the **Search Stats** comparison table shows
   BFS 58, UCS 69 and A\* 26 expansions. A\* reaches the same cost as UCS (4.45), and every
   algorithm finds a 3-term plan. Switch the algorithm radio from BFS to A\* to see the
   same thing one run at a time.
5. **Explain a chain.** Back on *Transfer*, open **Rule & Inference Log** and filter
   Rule to `OK`. Fall 2027 shows
   `CS301 · Completed(CS201) ∧ Completed(MATH210) ⇒ Eligible`. Those two facts were
   derived in Spring 2027, and in Fall 2027 they fire the rule that makes CS301 eligible.
   Open **Prerequisite Graph** and move **Current term** to see how the frontier advances.
6. **Watch the search.** Still on On-track at 12 credits, open **Watch the Search**.
   Press **Step ▶** a few times. The first steps are START, then EXPAND #0, which lists
   every course that is eligible and needed, then one PUSH per bundle. Press **▶ Play**
   to watch the tree grow (orange = being expanded, white = waiting in the frontier,
   dashed = skipped). Switch between A\* and BFS to see the difference in size, then
   **⏭ Run to end**: the solution path turns green, and A\* used 26 expansions against
   BFS's 58.
7. **Build my own plan.** Switch the sidebar **Mode** to **🧑‍🎓 Build my plan**. The
   student starts as On-track.
   - Tick **AI320**: it shows 🔒 `PREREQ: missing prerequisite(s): CS301`, and **Commit**
     is disabled.
   - Untick it and tick **CS301, CS310, MATH301**: all ✅. Commit the term.
   - In Spring 2027, press **🤖 Pick this term for me**. The AI ticks the first term of
     its optimal plan from where you are.
   - Press **🤖 Plan the rest for me**, then **Accept the AI's plan**. 🎓 All
     requirements are met.
   - Bonus: press **Start over**, switch to *Transfer* and tick **MATH210 + CS210**. You
     get ❌ `CONFLICT: both meet MW 10:00-11:30`.
8. **Bonus: persistence.** Press **Save plan**, open **Saved Plans**, select the row and
   press **Load**. The plan and the sidebar settings come back, and the app jumps to
   Semester Plan. **Delete** asks for confirmation, then removes the plan and its log rows.

## Limitations and possible extensions

- **Only maximal bundles.** Each term considers only bundles that can't take another
  eligible course. This keeps branching small and still finds the fewest-terms plan, but
  rules out deliberately light terms.
- **The rule log covers only the chosen plan.** States that were explored and discarded
  appear only in the stats.
- **Simplified time slots.** Slots are exact strings: `MW 10:00-11:30` and `M 10:00-11:00`
  don't count as overlapping.
- **No corequisite enforcement.** The schema and data model support corequisites, but the
  catalog has none and the rules only mention them.
- **Fixed calendar.** There are only two terms (fall and spring), no summer term, and no
  course capacity or instructor constraints.
- **Possible extensions:**
  - real time-interval overlap
  - corequisite rules (take X with Y)
  - a summer term
  - a GPA or workload model
  - editing the catalog from the UI, with cache-busting
  - exporting a plan to a calendar

## Git workflow

The history was built milestone by milestone, using
[Conventional Commits](https://www.conventionalcommits.org/). Each commit passes
`make test` and `make lint` and launches the app. Mistakes were fixed with new `fix:`
commits, never by amending. See `git log --oneline` for the history. The pre-commit
checklist and tooling notes are in [docs/development.md](docs/development.md).

Documentation beyond this README:
- [docs/decisions.md](docs/decisions.md): every place this build deviates from or
  interprets the brief
- [docs/architecture.md](docs/architecture.md): modules, schema, UI wiring, measured
  search results
- [docs/progress.md](docs/progress.md): milestone status
