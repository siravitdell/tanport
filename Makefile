# Works with GNU make on Windows (cmd or sh) and POSIX. Requires: docker, uv, node (>= 22.18).
UV := uv --directory backend run
NPM := npm --prefix frontend

.PHONY: help install up down dev test lint fmt migrate

help:
	@echo "make install  - install backend (uv) and frontend (npm) dependencies"
	@echo "make up       - start postgres + redis (docker compose)"
	@echo "make down     - stop them"
	@echo "make dev      - start infra, API (:8000), worker and web (:3000)"
	@echo "make test     - start infra, run pytest + frontend unit tests"
	@echo "make lint     - ruff + mypy (backend), eslint + tsc (frontend)"
	@echo "make fmt      - ruff format + ruff check --fix"
	@echo "make migrate  - alembic upgrade head"

install:
	uv --directory backend sync
	$(NPM) ci

up:
	docker compose up -d --wait

down:
	docker compose down

dev: up
	$(UV) python scripts/dev.py

test: up
	$(UV) pytest
	$(NPM) test

lint:
	$(UV) ruff check .
	$(UV) ruff format --check .
	$(UV) mypy
	$(NPM) run lint
	$(NPM) run typecheck

fmt:
	$(UV) ruff format .
	$(UV) ruff check --fix .

migrate: up
	$(UV) alembic upgrade head
