# CoursePath — a symbolic course planner

CoursePath plans a CS student's remaining semesters with classical symbolic AI. It has no
machine learning and makes no LLM calls. The course catalog is a knowledge base of facts:
prerequisites, term offerings, time slots and credits. Production rules decide which
courses are eligible and which are worth taking. Constraint pruning builds each term's
valid course bundles. BFS, UCS and A\* search over semester states for a plan that meets the
student's track requirements. Every rule that fires is logged, so the app can explain
*why* each course lands where it does.

It runs locally as a small web app: a Python JSON API (FastAPI) over the reasoning engine
and SQLite, and a hand-written HTML/CSS/JavaScript front end with no framework, no build
step and no external requests. The layout follows the SearchLab example.

The app has five views:

1. **AI planner:** pick a student, track, credit limit and algorithm. The plan updates
   live. Click any course to trace the rules that fired for it. Filter the rule & inference
   log by rule. Compare BFS, UCS and A\* side by side.
2. **Build my plan:** *you* pick the courses, term by term, by clicking course cards. The
   rule engine checks every click (✅ eligible, 🔒 missing a prerequisite, 📅 not offered
   this term, ⚠️ not needed for your track, ❌ time clash or over your credit limit) and
   explains each verdict. Hovering a locked course highlights the prerequisites it is
   waiting for. At any point you can ask the AI to pick this term or plan the rest from
   where you are.
3. **Watch the search:** replays a recorded search one event at a time, like a debugger.
   You get Step, Back, Play with a speed control, a scrubber and keyboard shortcuts. The
   tree grows as you step, and clicking a node shows its g, h and f values and the
   courses on its path.
4. **Prerequisite graph:** the whole catalog as a DAG, coloured by the term each course
   lands in. Click a course to light up its prerequisite chain and everything it unlocks.
5. **Saved plans:** plans stored in SQLite. Load one back into the planner, or delete it.

## How it maps to Symbolic AI

| Concept | Where it lives |
|---|---|
| **Knowledge representation** | Frozen dataclasses (`Course`, `StudentProfile`, `PlanState`) in `domain/models.py`. The catalog is a set of ground facts, persisted in SQLite. |
| **Production rules** | `reasoning/rules.py`: each rule is a condition ⇒ conclusion that returns a `RuleResult`. Example: `Completed(CS201) ∧ Completed(MATH210) ⇒ Eligible(CS301)` (`PREREQ`), `Offered(c, term)` (`OFFERING`), `CREDIT_CAP`, `CONFLICT`, and the relevance rule (`PRUNED`). |
| **Forward-chaining-style rule log** | `reasoning/explain.py` replays the chosen plan term by term. Facts derived in one term (newly completed courses) enable rules in the next, and each firing is recorded in order. |
| **Constraint pruning** | `reasoning/combos.py`: depth-first take/skip search that cuts any branch exceeding the credit cap or clashing on a time slot. The relevance rule also prunes courses that don't advance the goal. |
| **Heuristic search** | `reasoning/search.py`: BFS, UCS and A\* over `(completed set, term)` states. A\* uses an admissible, consistent heuristic. |
| **Watching the search** | `reasoning/trace.py` records every search event (expand, generate, skip duplicate or worse path, goal) so the **Watch the search** view can replay it step by step. |
| **Rule-based advising** | `reasoning/advisor.py` checks a student's own picks with the same rules and decides whether the term can be committed. The search can take over from any state the student reaches. |
| **Explanation interface** | `api/` serves every verdict, cost and event as JSON, and `web/` only displays them. The browser never re-implements a rule, so what you see is exactly what the Python engine (and its tests) computed. |

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). Node.js 18+ is optional and
only needed to run the front-end unit tests.

```bash
make run          # uv sync, then serve http://localhost:8000
```

Without make: `uv sync && uv run uvicorn api.server:app --port 8000`, then open
http://localhost:8000. The interactive API docs are at http://localhost:8000/api/docs.

`make test` runs the Python tests (pytest) and the JavaScript tests (`node --test`).
`make lint` runs ruff, and `make` on its own lists every target.

The SQLite database `courseplanner.db` is created and seeded automatically on first
launch. You don't need environment variables, secrets or a network service.

## Architecture

```text
courseplanner/
  Makefile               install / run / test / test-web / lint / reset-db / clean
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
  api/
    server.py            FastAPI app: JSON endpoints + serves web/
    serialize.py         dataclasses -> JSON
  web/
    index.html           single page, five views
    css/style.css        all styling
    js/                  app.js (router), api.js, util.js, layout.js (pure helpers),
                         planner.js, builder.js, watch.js, graph.js, saved.js
  tests/                 pytest, one file per layer; tests/web/ for node --test
  docs/                  design decisions, architecture, catalog, development notes
```

```text
domain/*.py --seed--> courseplanner.db --load--> Course / StudentProfile
                            ^                          |
                       save / load            rules -> combos -> search
                            |                          |
                            +------ PlanResult <-------+
                                        |
                              api/serialize.py -> JSON -> web/js views
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

Run `make run` and open http://localhost:8000. The planner starts with *On-track*, the AI
track, 18 credits per term and A\*.

1. **On-track + A\*.** The plan appears straight away, with 3 terms:
   - Fall 2026: *CS301, CS310, CS350, CS360, MATH301*
   - Spring 2027: *AI320, AI330, CS390*
   - Fall 2027: *AI401*

   That's 29 credits at cost 4.45. The comparison card shows A\* expanded 4 states,
   against 14 for BFS and 15 for UCS.
2. **Transfer.** Click *Transfer*. The plan grows to 4 terms, starting Spring 2027, and
   the catch-up courses CS201, MATH210 and CS210 get amber **catch-up** badges. Click
   **CS301** in the plan: the "Why this course?" card shows
   `Spring 2027: missing prerequisite(s): CS201, MATH210`, then
   `Completed(CS201) ∧ Completed(MATH210) ⇒ Eligible` in Fall 2027. That's forward
   chaining: facts derived in one term fire the rule in the next. In the rule log, click
   the chips so only `CONFLICT` stays on. You'll see
   `CS210/MATH210 · Spring 2027: both meet MW 10:00-11:30; cannot take both`.
3. **Tighter credit cap.** Click *On-track* and drag **Max credits per term** to 12. The
   plan is still 3 terms, because the prerequisite chain sets the length, not credits. The
   load spreads out to 10 / 10 / 9 credits, and the comparison card shows the search
   growing: BFS 58, UCS 69 and A\* 26 expansions. A\* and UCS agree on cost 4.45.
4. **Prerequisite graph.** Open view 4 and click **AI401**. Its five-deep chain lights up
   in amber: CS101 → CS201 → CS301 → AI320 → AI401, plus MATH101 → MATH210. That chain
   length is half of the A\* heuristic.
5. **Watch the search.** Open view 3 (On-track, 12 credits, A\*). Press **Step ▶** (or
   →) a few times. The first steps are START, then EXPAND #0, which lists every course
   that is eligible and needed, then one PUSH per bundle. Press **▶ Play**:
   - The tree grows, and the view follows the current node.
   - Orange means being expanded, white means waiting in the frontier, and dashed means
     skipped as a duplicate or worse path.

   Click any node to see its g, h and f values. Press **⏭ Run to end**: the solution path
   turns green, and the summary reads "A\* … 26 states … UCS 69, BFS 58". Switch to
   **BFS** to see a much bigger tree.
6. **Build my own plan.** Open view 2. The student starts as On-track.
   - Click **AI320**: it shows 🔒 *needs CS301*. Hovering it highlights CS301, and the
     Rule check panel shows `PREREQ`. **Commit** is disabled.
   - Click **SYS330**: you get ⚠️ `PRUNED not needed for track ai`.
   - Unpick both and press **🤖 Pick this term**: the AI ticks the first term of its
     optimal plan. Commit it.
   - Press **🤖 Plan the rest**, then **Accept the AI's plan**. 🎓 Every requirement is
     met. **↶ Undo last term** brings the last term's picks back.
   - Bonus: press **Start over** and choose *Transfer*. Pick **CS210 + MATH210**: you get
     ❌ `CONFLICT CS210/MATH210 both meet MW 10:00-11:30`.
7. **Persistence.** In the planner, press **💾 Save this plan**, then open view 5. Press
   **Load**: the plan comes back from SQLite with its settings. **Delete** asks for
   confirmation, then removes the plan and its rule-log rows.

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
  - editing the catalog from the UI (the API caches the catalog at startup)
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
- [docs/architecture.md](docs/architecture.md): modules, schema, API endpoints, front-end
  wiring, measured search results
- [docs/progress.md](docs/progress.md): milestone status
