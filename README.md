# AQIP — Autonomous QA Intelligence Platform

Multi-cloud, agent-native QA platform. See `docs/phases/README.md` for the phased implementation plan.

## Quick start

```bash
# Install workspace dependencies
uv sync --all-extras

# Run unit tests
uv run pytest tests/unit -q

# Lint + typecheck
uv run ruff check .
uv run mypy libs

# Start local infra
docker compose up -d   # requires Docker
```

## Layout

```
libs/          Shared libraries (aqip-core, aqip-events, aqip-vector, ...)
agents/        Agent implementations by tier
services/      HTTP/WebSocket entrypoints
workflows/     Step Functions / LangGraph definitions
infra/         IaC (AWS CDK, GCP cdktf, Modal SDK)
tests/         unit, integration, contract, e2e
docs/          ADRs, architecture, per-phase plans
config/        Per-cloud config, tenant config
```