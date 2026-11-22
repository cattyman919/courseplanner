# Progress

| # | Milestone | Status | Commit |
|---|---|---|---|
| 1 | Scaffold uv project, .gitignore, deps | done | `chore: scaffold uv project with streamlit and pytest` |
| 2 | Domain models, catalog, profiles | done | `feat(domain): add course, profile, and catalog seed data` |
| 3 | SQLite schema, seed, repo + tests | done | `feat(db): add sqlite schema, seed, and repository layer` |
| — | Makefile | done | `chore: add makefile for install, run, test, and lint` |
| 4 | Rules + tests | done | `feat(rules): implement eligibility, schedule, and goal checks` |
| 5 | Combo generator + tests | done | `feat(combos): add pruned dfs combo generator` |
| — | Ruff fix + pinned dev dependency | done | `fix(db): ...`, `chore: pin ruff ...` |
| — | Project docs | done | `docs: add project docs for decisions, catalog, and architecture` |
| 6 | BFS + UCS planners + tests | done | `feat(search): add bfs and ucs planners` |
| 7 | A* + heuristic + A* == UCS test | done | `feat(search): add a* with admissible heuristic` |
| 8 | Rule-log summariser | done | `feat(explain): add rule-log summarizer` |
| 9 | Streamlit UI (plans render) | done | `feat(ui): wire planner into streamlit` |
| 10 | Saved-plans tab | done | `feat(ui): add saved plan persistence` |
| 11 | README, demo script | done | `docs: add readme, demo script, and architecture notes` |

## Acceptance criteria (§15)

| Criterion | Status |
|---|---|
| `uv sync && uv run streamlit run app.py` launches; DB auto-created and seeded | ✅ |
| `rm courseplanner.db` then relaunch recreates and reseeds | ✅ 25 courses, 3 profiles, `user_version = 1` |
| All 3 scenarios plan under BFS, UCS, A\* | ✅ tested at 12, 15, 18 credits |
| Transfer log shows a `PREREQ` and a `CONFLICT` | ✅ `CS301` / `CS210/MATH210` |
| A\* cost == UCS cost on all scenarios (test-enforced) | ✅ |
| Search stats populate and are non-zero | ✅ |
| Prerequisite graph renders with coloured nodes | ✅ (AppTest; not yet eyeballed in a browser) |
| Save → appears → load restores → delete removes | ✅ (AppTest end-to-end) |
| `uv run pytest -q` passes, including DB tests | ✅ 115 tests |
| Conventional-commit history, one per milestone | ✅ 11 milestones + 4 support commits (D8) |
| `git status` clean; `.venv/`, `__pycache__/`, DB untracked | ✅ |
| No network calls, no LLM calls, no remote DB | ✅ |
| README demo script matches actual app behaviour | ✅ replayed step by step with AppTest |
