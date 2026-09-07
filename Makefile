# IntelliqX Makefile

.PHONY: help install sync lint typecheck vulture format coverage test test-unit \
        test-contract test-integration test-e2e test-sgir run-agent cover \
        docker-up docker-down clean

UV       ?= uv
PY       ?= $(UV) run python
AGENT    ?=

help:
	@echo "IntelliqX targets:"
	@echo "  make install           Install workspace dependencies"
	@echo "  make sync              uv sync --all-packages"
	@echo "  make lint              ruff check ."
	@echo "  make format            ruff format ."
	@echo "  make typecheck         mypy libs agents"
	@echo "  make vulture           vulture on libs/ agents/ tests/"
	@echo "  make coverage          Run pytest with coverage report (fail under 95%)"
	@echo "  make test              Run all tests"
	@echo "  make test-unit         Run unit tests"
	@echo "  make test-contract     Run contract tests"
	@echo "  make test-integration  Run integration tests"
	@echo "  make test-e2e          Run end-to-end tests"
	@echo "  make test-sgir         Run SGIR graph intelligence tests"
	@echo "  make run-agent AGENT=execution/execution"
	@echo "                         Run a specific agent module (category/agent)"
	@echo "  make cover             Same as coverage"
	@echo "  make docker-up         Start docker compose (core services)"
	@echo "  make docker-down       Stop docker compose"

install:
	$(UV) sync --all-packages

sync:
	$(UV) sync --all-packages

lint:
	$(UV) run ruff check .

format:
	$(UV) run ruff format .

typecheck:
	$(UV) run mypy libs agents

vulture:
	$(UV) run vulture libs agents tests .vulture-whitelist

coverage:
	$(UV) run python -m coverage run --source=intelliqx -m pytest tests/unit tests/contract tests/integration
	$(UV) run python -m coverage report

cover: coverage

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

test-sgir:
	$(UV) run pytest tests/unit/test_sgir -q

run-agent:
	@if [ -z "$(AGENT)" ]; then echo "Usage: make run-agent AGENT=<category>/<agent>"; exit 1; fi
	$(UV) run python -m agents.$(AGENT).agent

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	rm -rf .venv build dist **/__pycache__ **/*.pyc .pytest_cache .coverage