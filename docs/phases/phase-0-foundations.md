# Phase 0 — Foundations

**Goal**: Stand up the IntelliqX monorepo, shared libs, local infra config, and CI so every subsequent phase can build on a verified base.

**Status**: COMPLETE

---

## 0.1 Scope

| Area | Deliverable |
|---|---|
| Monorepo | `uv` workspace with `libs/`, `agents/`, `tests/`, `docs/`, `infra/local/` |
| Shared libs | `intelliqx-core`, `intelliqx-agents`, `intelliqx-events`, `intelliqx-storage`, `intelliqx-vector` (zvec + sqlite-vec), `intelliqx-kg` (DuckDB+Parquet), `intelliqx-llm`, `intelliqx-state`, `intelliqx-compute`, `intelliqx-observability`, `intelliqx-tools`, `intelliqx-okf` (OKF bundles + catalog) |
| Local infra | `docker-compose.yml` (Redpanda, Redis, MinIO, LiteLLM, Temporal, Jaeger, Prometheus, Grafana) and in-process test adapters |
| CI | GitHub Actions: lint (ruff), typecheck (mypy), unit tests (pytest), contract tests |
| Schemas | Event JSON Schemas, OpenAPI 3.1, KG parquet schema v1 |
| Docs | Architecture C4 (Structurizr DSL), ADRs 0001–0012, agent catalog stub |

## 0.2 Architecture decisions locked in this phase

- **ADR-0001**: Python 3.12+ monorepo managed by `uv` workspaces.
- **ADR-0003**: zvec as the embedded vector store.
- **ADR-0004**: Knowledge Graph as Parquet files + DuckDB queries (no managed graph DB).
- **ADR-0005**: In-process Pub/Sub-style event bus with DLQ semantics.
- **ADR-0009**: Local testing via in-process adapters.
- **ADR-0010**: Pydantic v2 for value objects.
- **ADR-0011**: OKF catalog with hybrid retrieval.
- **ADR-0012**: litellm-based LLM abstraction with the Fake and MiniMax backends.

## 0.3 Deliverables checklist

- [x] `pyproject.toml` workspace + per-package `pyproject.toml`s
- [x] `Dockerfile.agent` template
- [x] `docker-compose.yml`
- [x] `intelliqx-core` (Pydantic models, enums, errors, event base)
- [x] `intelliqx-events` (EventBus interface + in-memory impl)
- [x] `intelliqx-storage` (ObjectStore interface + in-memory + local filesystem impls)
- [x] `intelliqx-vector` (VectorIndex interface + zvec impl + persistence)
- [x] `intelliqx-kg` (KG query API on DuckDB+Parquet)
- [x] `intelliqx-state` (in-memory impl)
- [x] `intelliqx-llm` (LLMClient interface + Fake + MiniMax adapters)
- [x] `intelliqx-compute` (ComputeRuntime interface + in-process impl)
- [x] `intelliqx-observability` (OTel + structured logging)
- [x] `intelliqx-agents` (AgentBase + decorators)
- [x] `intelliqx-tools` (ToolManager + MCP scaffolding)
- [x] Schemas: `schemas/events/*.json`
- [x] GitHub Actions: `.github/workflows/ci.yml`
- [x] ADRs: `docs/adr/0001..0012.md`
- [x] `intelliqx-okf` (OKF bundles, catalog, validator)
- [x] Unit + contract test suites green

## 0.4 Test/verification criteria

1. **Workspace integrity**: `uv sync` resolves all packages; `uv run pytest tests/unit` 100% green.
2. **Type safety**: `uv run mypy libs` and `uv run mypy agents` exit 0.
3. **Lint clean**: `uv run ruff check .` exits 0.
4. **Event contract**: every event schema validates against sample payloads (positive + negative tests).
5. **In-process agents**: an agent written against the interfaces runs end-to-end via `InProcessComputeRuntime` and the in-memory stores.
6. **KG smoke**: ingest 1k nodes/5k edges → 10 representative queries return correct results in <1s.
7. **Vector smoke**: index 10k random vectors (768d) → query top-10 with recall@10 ≥ 0.95 vs brute-force.

## 0.5 Out of scope

- Any concrete agent implementation (deferred to Phases 3–6).
- External deployment infrastructure.
- Real LLM calls in tests (use `intelliqx-llm.fake`).

## 0.6 Risks

| Risk | Mitigation |
|---|---|
| zvec Python bindings not on PyPI for our Python 3.13 | Pin Python 3.12 in `.python-version`; fallback to Chroma if zvec unavailable |
| DuckDB+Parquet KG doesn't scale to >10M edges | Partition pruning + columnar compression; benchmark in Phase 0 test |
