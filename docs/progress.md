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
| — | Search trace (D9) | done | `feat(search): record step-by-step search trace` |
| — | Advisor rule checks (D9) | done | `feat(advisor): check student-chosen terms with the rule engine` |
| — | Build my plan + Watch the Search UI (D9) | done | `feat(ui): add build-my-plan mode and step-through search viewer` |
| — | Docs for interactive modes | done | `docs: document interactive modes and extend demo script` |
| — | JSON API over the engine (D10) | done | `feat(api): serve rules, search, and saved plans as a JSON API` |
| — | HTML/JS front end (D10) | done | `feat(web): add HTML/JS front end with planner, builder, and search replay` |
| — | Graph + saved plans views (D10) | done | `feat(web): add interactive prerequisite graph and saved plans view` |
| — | Remove Streamlit (D10) | done | `refactor: remove Streamlit UI in favour of the web front end` |
| — | Docs for the web app | done | `docs: document the web app and the move away from Streamlit` |
| — | UI review fixes: keyboard, focus | done | `fix(web): keep keyboard focus and make every control keyboard-operable` |
| — | UI review fixes: contrast, text size | done | `fix(web): raise text contrast to 4.5:1 and set a 12px minimum size` |
| — | UI review fixes: motion, screen readers | done | `fix(web): respect reduced motion and announce results to screen readers` |

## Acceptance criteria (§15)

| Criterion | Status |
|---|---|
| App launches (`make run`, now FastAPI + HTML/JS instead of Streamlit, see D10); DB auto-created and seeded | ✅ |
| `rm courseplanner.db` then relaunch recreates and reseeds | ✅ 25 courses, 3 profiles, `user_version = 1` |
| All 3 scenarios plan under BFS, UCS, A\* | ✅ tested at 12, 15, 18 credits |
| Transfer log shows a `PREREQ` and a `CONFLICT` | ✅ `CS301` / `CS210/MATH210` |
| A\* cost == UCS cost on all scenarios (test-enforced) | ✅ |
| Search stats populate and are non-zero | ✅ |
| Prerequisite graph renders with coloured nodes | ✅ (headless Chromium, screenshots checked) |
| Save → appears → load restores → delete removes | ✅ (API tests + headless Chromium) |
| `uv run pytest -q` passes, including DB tests | ✅ 181 Python tests + 8 JS tests |
| Conventional-commit history, one per milestone | ✅ 11 milestones + 4 support commits (D8) |
| `git status` clean; `.venv/`, `__pycache__/`, DB untracked | ✅ |
| No network calls, no LLM calls, no remote DB | ✅ |
| README demo script matches actual app behaviour | ✅ numbers checked against the API and in the browser |
