.PHONY: setup start dev demo test build

# Change with: make start PORT=7500
PORT ?= 7420
export ACC_PORT := $(PORT)

# Keep project memory inside an Obsidian vault: make start MEMORY_DIR=~/Obsidian/Orbit
ifdef MEMORY_DIR
export ACC_MEMORY_DIR := $(MEMORY_DIR)
endif

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
	(cd server && uv run uvicorn acc.main:app --host 127.0.0.1 --port $(PORT) --reload) & \
	(cd web && npm run dev) & \
	wait

test:
	cd server && uv run ruff check acc tests && uv run pytest -q
	cd web && npm run typecheck
