# Dev loop. Backend needs uv (https://docs.astral.sh/uv/), frontend needs node 22+.

.PHONY: backend frontend dev test lint check build docker

backend:
	cd backend && uv run uvicorn draftkit.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

dev:
	$(MAKE) -j2 backend frontend

test:
	cd backend && uv run pytest
	cd frontend && npx tsc -b

# Coverage is enforced in pytest's addopts; this just shows the report.
coverage:
	cd backend && uv run pytest --cov-report=term-missing

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint

typecheck:
	cd backend && uv run pyright

check: lint test

build:
	cd frontend && npm run build

# Run the production shape locally: one process serving API + built UI.
serve: build
	cd backend && DRAFTKIT_STATIC_DIR=../frontend/dist uv run uvicorn draftkit.main:app --port 8000

# Regenerate docs/data-sources.md from the adapters themselves.
docs:
	cd backend && uv run python -c "from draftkit.sources import registry; from pathlib import Path; Path('../docs/data-sources.md').write_text(registry.as_markdown())"

# What each source actually returns vs what it claims. Add --live before a draft.
census:
	cd backend && uv run python scripts/census.py

docker:
	docker build -f docker/Dockerfile -t draftkit .

# End-to-end smoke against a running server (see e2e/README section below).
# Start the app with `make serve` in another shell first.
e2e:
	npm run e2e
