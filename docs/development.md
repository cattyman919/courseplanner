# Development

## Setup

```bash
make install        # uv sync (fastapi, uvicorn; dev: pytest, ruff, httpx)
make run            # uvicorn api.server:app on http://localhost:8000; creates + seeds courseplanner.db
```

No environment variables, secrets, network services, or LLM calls.

## Makefile targets

| Target | Command |
|---|---|
| `make` / `make help` | list targets |
| `make install` | `uv sync` |
| `make run` | install, then `uv run uvicorn api.server:app --port 8000` |
| `make test` | `uv run pytest -q`, then `make test-web` if Node.js is installed |
| `make test-web` | `node --test tests/web/*.mjs` (front-end helpers) |
| `make lint` | `uv run ruff check .` (line length 100) |
| `make reset-db` | delete `courseplanner.db`; recreated on next run |
| `make clean` | remove `.pytest_cache`, `.ruff_cache`, `__pycache__` |

## Tests

One file per layer in `tests/`. pytest is configured in `pyproject.toml`
(`pythonpath = ["."]`). DB tests use a per-test `tmp_path` database and never touch
`courseplanner.db`.

## Tests for the API and the browser

- `tests/test_api.py` drives the FastAPI app with `TestClient` against a temporary
  database. It checks that the JSON matches the engine (plans, costs, expansion counts,
  verdicts, conflicts), the save/load/delete round-trip, and the 422s for bad input.
- `tests/web/test_layout.mjs` unit-tests the pure front-end helpers.
- **End-to-end:** the views were driven in headless Chromium through the Chrome DevTools
  Protocol, the same approach as SearchLab's `tools/ui_smoke.js`. Every view was clicked
  through, with screenshots, the console checked for errors, and a check for no
  horizontal overflow at phone width. This needs a local Chromium, so it is a manual check
  and not part of `make test`.

## Pre-commit checklist (§13.4)

1. `git status` — no stray files.
2. `make test` — all green.
3. `make lint` — clean.
4. Smoke test: `make run`, check `GET /api/profiles` returns 3 profiles, stop it.
5. `git diff --staged`, then commit with a Conventional Commit message (≤ 72 chars).

Never amend or force-push; mistakes get a new `fix:` commit.

## Known issue: first ruff download

On first install the ruff wheel download from PyPI stalled (no proxy or uv config
involved; PyPI itself responded normally). Once cached, `uv run ruff` takes well under a
second. If `make install` hangs on ruff, interrupt and rerun it.
