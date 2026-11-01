.PHONY: setup start dev demo test build

setup:
	cd server && uv sync
	cd web && npm install && npm run build

build:
	cd web && npm run build

# Single port: backend serves the built UI.
start: build
	cd server && uv run python -m acc.main

demo: build
	cd server && ACC_DEMO=1 uv run python -m acc.main

# Backend + Vite hot reload. Ctrl+C stops both.
dev:
	@trap 'kill 0' INT TERM EXIT; \
	(cd server && uv run uvicorn acc.main:app --host 127.0.0.1 --port 8765 --reload) & \
	(cd web && npm run dev) & \
	wait

test:
	cd server && uv run ruff check acc tests && uv run pytest -q
	cd web && npm run typecheck
