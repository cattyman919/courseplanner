.PHONY: help install run test lint reset-db clean
.DEFAULT_GOAL := help

help: ## Show available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-10s %s\n", $$1, $$2}'

install: ## Install dependencies with uv
	uv sync

run: install ## Launch the Streamlit app (creates and seeds the DB on first run)
	uv run streamlit run app.py

test: ## Run the test suite
	uv run pytest -q

lint: ## Lint with ruff
	uv run ruff check .

reset-db: ## Delete the local SQLite DB; it is recreated on next run
	rm -f courseplanner.db courseplanner.db-journal

clean: ## Remove caches
	rm -rf .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -not -path "./.venv/*" -exec rm -rf {} +
