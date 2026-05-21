# ============================================================
# Lumenis AI — Makefile (Developer Convenience Commands)
# ============================================================

.PHONY: dev down logs backend-shell db-migrate db-revision test lint clean backend-dev celery-dev help

# Default target
.DEFAULT_GOAL := help

# ---------- Docker ----------

## Start the full development stack (build & run)
dev:
	docker compose up --build

## Stop all containers
down:
	docker compose down

## Follow logs for all services
logs:
	docker compose logs -f

## Open a shell inside the backend container
backend-shell:
	docker compose exec backend /bin/bash

# ---------- Database ----------

## Run Alembic migrations (upgrade to head)
db-migrate:
	docker compose exec backend alembic upgrade head

## Create a new Alembic revision (usage: make db-revision msg="add users table")
db-revision:
	docker compose exec backend alembic revision --autogenerate -m "$(msg)"

# ---------- Quality ----------

## Run the test suite with pytest
test:
	docker compose exec backend python -m pytest tests/ -v --tb=short

## Lint the codebase with ruff
lint:
	docker compose exec backend python -m ruff check app/ tests/

# ---------- Cleanup ----------

## Remove all containers, networks, and named volumes
clean:
	docker compose down -v --remove-orphans
	docker system prune -f

# ---------- Local Development (no Docker) ----------

## Run the backend locally with hot-reload
backend-dev:
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

## Run the Celery worker locally
celery-dev:
	cd backend && celery -A app.workers.celery_app worker --loglevel=info

# ---------- Help ----------

## Show this help message
help:
	@echo ""
	@echo "  Lumenis AI — Available Commands"
	@echo "  ================================"
	@echo ""
	@echo "  Docker:"
	@echo "    make dev              Start the full dev stack (build & run)"
	@echo "    make down             Stop all containers"
	@echo "    make logs             Follow logs for all services"
	@echo "    make backend-shell    Shell into the backend container"
	@echo ""
	@echo "  Database:"
	@echo "    make db-migrate       Run Alembic migrations (upgrade head)"
	@echo "    make db-revision      Create a new migration (msg=\"description\")"
	@echo ""
	@echo "  Quality:"
	@echo "    make test             Run pytest"
	@echo "    make lint             Run ruff linter"
	@echo ""
	@echo "  Cleanup:"
	@echo "    make clean            Remove containers, volumes, prune images"
	@echo ""
	@echo "  Local (no Docker):"
	@echo "    make backend-dev      Run backend with uvicorn --reload"
	@echo "    make celery-dev       Run Celery worker locally"
	@echo ""
