SHELL := /bin/bash

PYTHON ?= python3
PNPM ?= pnpm
# Prefer a normal Node installation. Codex desktop bundles Node outside PATH, so
# discover that runtime as a local fallback without changing normal user setups.
SYSTEM_NODE_BIN_DIR := $(dir $(shell command -v node 2>/dev/null))
CODEX_NODE_BIN_DIR := $(dir $(firstword $(wildcard $(HOME)/.cache/codex-runtimes/*/dependencies/node/bin/node)))
NODE_BIN_DIR := $(if $(SYSTEM_NODE_BIN_DIR),$(SYSTEM_NODE_BIN_DIR),$(CODEX_NODE_BIN_DIR))
FRONTEND_ENV := PATH="$(NODE_BIN_DIR):$$PATH"
BACKEND_DIR := backend
FRONTEND_DIR := frontend
BACKEND_VENV := $(BACKEND_DIR)/.venv
BACKEND_PYTHON := $(BACKEND_VENV)/bin/python
BACKEND_UVICORN := $(BACKEND_VENV)/bin/uvicorn
BACKEND_ALEMBIC := $(BACKEND_VENV)/bin/alembic
BACKEND_PYTEST := $(BACKEND_VENV)/bin/pytest
BACKEND_RUFF := $(BACKEND_VENV)/bin/ruff

.PHONY: help install check-deps migrate migration-test dev test \
	backend-test frontend-test typecheck backend-lint frontend-lint lint build clean

help:
	@echo "Adaptive Training Coach"
	@echo "  make install        Create the backend venv and install locked frontend deps"
	@echo "  make dev            Migrate and run FastAPI + Vite"
	@echo "  make test           Run tests, typecheck, lint, build, and migration smoke test"
	@echo "  make migrate        Apply Alembic migrations to the configured local database"
	@echo "  make clean          Remove generated caches and frontend build output only"

install:
	@test -d "$(BACKEND_VENV)" || $(PYTHON) -m venv "$(BACKEND_VENV)"
	@cd "$(BACKEND_DIR)" && .venv/bin/python -m pip install -e '.[dev]'
	@$(FRONTEND_ENV) $(PNPM) --dir "$(FRONTEND_DIR)" install --frozen-lockfile

check-deps:
	@test -x "$(BACKEND_PYTHON)" || { echo "Backend dependencies missing; run 'make install'." >&2; exit 1; }
	@$(FRONTEND_ENV) command -v node >/dev/null || { echo "Node.js is required; install Node 20.19+ or 22.12+." >&2; exit 1; }
	@$(FRONTEND_ENV) command -v "$(PNPM)" >/dev/null || { echo "pnpm is required; install/enable it, then run 'make install'." >&2; exit 1; }
	@test -d "$(FRONTEND_DIR)/node_modules" || { echo "Frontend dependencies missing; run 'make install'." >&2; exit 1; }

migrate: check-deps
	@mkdir -p "$(BACKEND_DIR)/data"
	@cd "$(BACKEND_DIR)" && .venv/bin/python -m app.migration_bootstrap
	@cd "$(BACKEND_DIR)" && .venv/bin/alembic upgrade head

dev: migrate
	@set -e; \
		(cd "$(BACKEND_DIR)" && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) & \
		backend_pid=$$!; \
		trap 'kill $$backend_pid 2>/dev/null || true' EXIT INT TERM; \
		$(FRONTEND_ENV) $(PNPM) --dir "$(FRONTEND_DIR)" run dev

backend-test: check-deps
	@cd "$(BACKEND_DIR)" && .venv/bin/pytest

frontend-test: check-deps
	@$(FRONTEND_ENV) $(PNPM) --dir "$(FRONTEND_DIR)" run test

typecheck: check-deps
	@$(FRONTEND_ENV) $(PNPM) --dir "$(FRONTEND_DIR)" run typecheck

backend-lint: check-deps
	@cd "$(BACKEND_DIR)" && .venv/bin/ruff check app tests alembic
	@cd "$(BACKEND_DIR)" && .venv/bin/ruff format --check app tests alembic

frontend-lint: check-deps
	@$(FRONTEND_ENV) $(PNPM) --dir "$(FRONTEND_DIR)" run lint

lint: backend-lint frontend-lint

build: check-deps
	@$(FRONTEND_ENV) $(PNPM) --dir "$(FRONTEND_DIR)" run build

migration-test: check-deps
	@temp_dir=$$(mktemp -d); \
		trap 'rm -rf "$$temp_dir"' EXIT; \
		cd "$(BACKEND_DIR)"; \
		DATABASE_URL="sqlite:///$$temp_dir/migration.db" .venv/bin/python -m app.migration_bootstrap; \
		DATABASE_URL="sqlite:///$$temp_dir/migration.db" .venv/bin/alembic upgrade head; \
		DATABASE_URL="sqlite:///$$temp_dir/migration.db" .venv/bin/alembic check

test: backend-test frontend-test typecheck lint build migration-test

clean:
	@rm -rf "$(FRONTEND_DIR)/dist" "$(FRONTEND_DIR)/coverage"
	@rm -rf "$(BACKEND_DIR)/.pytest_cache" "$(BACKEND_DIR)/.ruff_cache" "$(BACKEND_DIR)/htmlcov"
	@find "$(BACKEND_DIR)/app" "$(BACKEND_DIR)/tests" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
