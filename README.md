# IntelliqX — Autonomous QA Intelligence Platform

Multi-cloud, agent-native QA platform with 29 agents across 15 independent libraries. See `docs/phases/README.md` for the phased implementation plan and [`docs/adr/`](docs/adr/) for Architecture Decision Records.

## Quick start

```bash
# Install workspace dependencies
uv sync --all-extras

# Run unit + integration tests
uv run pytest tests/unit tests/integration -q

# Lint + typecheck
uv run ruff check .
uv run mypy libs

# Start local infra
docker compose up -d   # requires Docker
```

## Layout

```
libs/          15 shared libraries (intelliqx-core, intelliqx-events, intelliqx-vector, intelliqx-okf, ...)
agents/        29 agent implementations, grouped by category
  coordination/  Planner, Orchestrator, Memory, Knowledge/RAG, Tool Manager, Smoke
  intelligence/  Requirements Intel, Code Intel, Risk, Test Design, Test Data, Coverage, Critic, Learning, Prompt Mgmt
  execution/     Environment, Design Intel, Execution, Self-Healing, Failure Analysis, Visual Regression, A11y, Perf, Security, Cost Opt
  governance/    Observability, Reporting, Governance & Compliance, Release Readiness
schemas/       Event JSON Schemas, KG schema
dashboards/    Dashboard definitions
prompts/       Prompt templates
scripts/       Utility scripts
services/      HTTP/WebSocket entrypoints
workflows/     Step Functions / LangGraph definitions
infra/         IaC (AWS CDK, GCP cdktf, Modal SDK)
tests/         unit, integration, contract, e2e
docs/          ADRs, architecture, per-phase plans
config/        Per-cloud config, tenant config
```