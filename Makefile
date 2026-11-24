# Works with GNU make on Windows (cmd or sh) and POSIX. Requires: docker, uv.
UV := uv --directory backend run

.PHONY: help up down dev test lint fmt migrate

help:
	@echo "make up       - start postgres + redis (docker compose)"
	@echo "make down     - stop them"
	@echo "make dev      - start infra, API (:8000) and worker"
	@echo "make test     - start infra, run pytest"
	@echo "make lint     - ruff check + ruff format --check + mypy"
	@echo "make fmt      - ruff format + ruff check --fix"
	@echo "make migrate  - alembic upgrade head"

up:
	docker compose up -d --wait

down:
	docker compose down

dev: up
	$(UV) python scripts/dev.py

test: up
	$(UV) pytest

lint:
	$(UV) ruff check .
	$(UV) ruff format --check .
	$(UV) mypy

fmt:
	$(UV) ruff format .
	$(UV) ruff check --fix .

migrate: up
	$(UV) alembic upgrade head
