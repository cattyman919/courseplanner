.PHONY: help install run test test-web lint reset-db clean demo-video demo-clean
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

FFMPEG_FULL := $(shell brew --prefix ffmpeg-full 2>/dev/null)/bin

demo-video: ## Record + render the narrated demo to demo/output/ (needs Node 22.6+, uv, ffmpeg-full)
	@test -x "$(FFMPEG_FULL)/ffmpeg" || { echo "Needs ffmpeg with libass: brew install ffmpeg-full"; exit 1; }
	cd demo && npm ci --no-audit --no-fund && npx playwright install chromium
	cd demo && PATH="$(FFMPEG_FULL):$$PATH" npx playwright test
	cd demo && PATH="$(FFMPEG_FULL):$$PATH" node render.ts

demo-clean: ## Remove demo recordings and renders (keeps the cached voice model)
	rm -rf demo/output demo/test-results demo/playwright-report
