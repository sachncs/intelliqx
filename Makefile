# IntelliqX Makefile

.PHONY: help install sync lint typecheck test test-unit test-contract test-e2e \
        clean run-agent eval tier=% docs build docker-up docker-down

UV       ?= uv
PY       ?= $(UV) run python
AGENT    ?=

help:
	@echo "IntelliqX targets:"
	@echo "  make install      Install workspace dependencies"
	@echo "  make sync         uv sync --all-packages"
	@echo "  make lint         ruff check ."
	@echo "  make typecheck    mypy libs agents"
	@echo "  make test         Run all tests"
	@echo "  make test-unit    Run unit tests"
	@echo "  make test-contract"
	@echo "  make test-e2e"
	@echo "  make eval tier=N  Run evals for tier N"
	@echo "  make run-agent AGENT=tier3/execution"
	@echo "  make docker-up    Start docker compose (core services)"

install:
	$(UV) sync --all-packages

sync:
	$(UV) sync --all-packages

lint:
	$(UV) run ruff check .

typecheck:
	$(UV) run mypy libs || true

test:
	$(UV) run pytest -q

test-unit:
	$(UV) run pytest tests/unit -q

test-contract:
	$(UV) run pytest tests/contract -q

test-integration:
	$(UV) run pytest tests/integration -q

test-e2e:
	$(UV) run pytest tests/e2e -q -m e2e

eval:
	@if [ -z "$(tier)" ]; then echo "Usage: make eval tier=N"; exit 1; fi
	$(UV) run pytest evals/tier$(tier) -q

run-agent:
	@if [ -z "$(AGENT)" ]; then echo "Usage: make run-agent AGENT=tier3/execution"; exit 1; fi
	$(UV) run python -m agents.$(AGENT).agent

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	rm -rf .venv build dist **/__pycache__ **/*.pyc .pytest_cache .coverage