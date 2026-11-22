# Development

## Setup

```bash
make install        # uv sync (streamlit, pytest, ruff)
make run            # uv run streamlit run app.py; creates + seeds courseplanner.db
```

No environment variables, secrets, network services, or LLM calls.

## Makefile targets

| Target | Command |
|---|---|
| `make` / `make help` | list targets |
| `make install` | `uv sync` |
| `make run` | install, then `uv run streamlit run app.py` |
| `make test` | `uv run pytest -q` |
| `make lint` | `uv run ruff check .` (line length 100) |
| `make reset-db` | delete `courseplanner.db`; recreated on next run |
| `make clean` | remove `.pytest_cache`, `.ruff_cache`, `__pycache__` |

## Tests

One file per layer in `tests/`. pytest is configured in `pyproject.toml`
(`pythonpath = ["."]`). DB tests use a per-test `tmp_path` database and never touch
`courseplanner.db`.

## UI checks

Streamlit's `AppTest` (`streamlit.testing.v1`) can drive `app.py` headlessly: set sidebar
widgets via `at.sidebar.selectbox[...]`, click **Generate plan**, and assert
`not at.exception`. Target `at.sidebar.*` explicitly — after a plan renders, the main area
has its own selectbox. `st.badge` renders as markdown (`:red-badge[...]`), so look for it in
`at.markdown`. AppTest runs `init_db()` against the real `courseplanner.db`, which is why it
is used for manual checks rather than in `tests/`.

## Pre-commit checklist (§13.4)

1. `git status` — no stray files.
2. `make test` — all green.
3. `make lint` — clean.
4. Streamlit smoke test: launch headless, wait for `/_stcore/health` to return `ok`, stop it.
5. `git diff --staged`, then commit with a Conventional Commit message (≤ 72 chars).

Never amend or force-push; mistakes get a new `fix:` commit.

## Known issue: first ruff download

On first install the ruff wheel download from PyPI stalled (no proxy or uv config
involved; PyPI itself responded normally). Once cached, `uv run ruff` takes well under a
second. If `make install` hangs on ruff, interrupt and rerun it.
