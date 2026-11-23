.PHONY: help install run test test-web lint reset-db clean
.DEFAULT_GOAL := help

help: ## Show available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-10s %s\n", $$1, $$2}'

install: ## Install dependencies with uv
	uv sync

run: install ## Launch the web app at http://localhost:8000 (creates and seeds the DB on first run)
	@echo "CoursePath: http://localhost:8000"
	uv run uvicorn api.server:app --port 8000

test: ## Run the Python and JavaScript test suites
	uv run pytest -q
	@command -v node >/dev/null && $(MAKE) --no-print-directory test-web || echo "node not found; skipped JS tests"

test-web: ## Run the front-end unit tests (needs Node.js 18+)
	node --test tests/web/*.mjs

lint: ## Lint with ruff
	uv run ruff check .

reset-db: ## Delete the local SQLite DB; it is recreated on next run
	rm -f courseplanner.db courseplanner.db-journal

clean: ## Remove caches
	rm -rf .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -not -path "./.venv/*" -exec rm -rf {} +
