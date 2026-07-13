# Phase 0 — Foundations

**Goal**: Stand up the IntelliqX monorepo, portability layer, shared libs, local infra config, and CI so every subsequent phase can build on a verified base.

**Status**: COMPLETE

---

## 0.1 Scope

| Area | Deliverable |
|---|---|
| Monorepo | `uv` workspace with `libs/`, `agents/`, `services/`, `workflows/`, `tests/`, `docs/`, `infra/`, `config/` |
| Shared libs | `intelliqx-core`, `intelliqx-agents`, `intelliqx-portability`, `intelliqx-events`, `intelliqx-storage`, `intelliqx-vector` (zvec + sqlite-vec), `intelliqx-kg` (DuckDB+Parquet), `intelliqx-llm`, `intelliqx-state`, `intelliqx-compute`, `intelliqx-observability`, `intelliqx-tools`, `intelliqx-okf` (OKF bundles + catalog) |
| Local infra | `docker-compose.yml` (Redpanda, Redis, MinIO, LiteLLM, Temporal, Jaeger, Prometheus, Grafana) and in-process test adapters |
| CI | GitHub Actions: lint (ruff), typecheck (mypy), unit tests (pytest), contract tests |
| Schemas | Event JSON Schemas, OpenAPI 3.1, KG parquet schema v1 |
| Docs | Architecture C4 (Structurizr DSL), ADRs 0001–0010, agent catalog stub |

## 0.2 Architecture decisions locked in this phase

- **ADR-0001**: Python 3.12+ monorepo managed by `uv` workspaces.
- **ADR-0002**: Multi-cloud portability via `intelliqx-portability` (no direct boto3/google-cloud/modal in agent code).
- **ADR-0003**: zvec as the embedded vector store; persisted to object storage per cloud.
- **ADR-0004**: Knowledge Graph as Parquet files + DuckDB queries (no managed graph DB).
- **ADR-0005**: Pub/Sub semantics for event bus; EventBridge+SQS / Pub/Sub / modal.Queue.
- **ADR-0006**: AWS CDK for AWS, cdktf for GCP, Modal native SDK for Modal deployment.

## 0.3 Deliverables checklist

- [ ] `pyproject.toml` workspace + per-package `pyproject.toml`s
- [ ] `Dockerfile.agent` template (multi-stage, distroless runtime)
- [ ] `docker-compose.yml`, `docker-compose.observability.yml`
- [ ] `intelliqx-portability` (CloudAdapter + 3 impls + local impl)
- [ ] `intelliqx-core` (Pydantic models, enums, errors, event base)
- [ ] `intelliqx-events` (EventBus interface + 3 cloud impls + in-memory impl)
- [ ] `intelliqx-storage` (ObjectStore interface + 3 cloud impls + local filesystem impl)
- [ ] `intelliqx-vector` (VectorIndex interface + zvec impl + persistence)
- [ ] `intelliqx-kg` (KG query API on DuckDB+Parquet)
- [ ] `intelliqx-state` (Redis client + Upstash client + in-memory impl)
- [ ] `intelliqx-llm` (LLMClient interface + adapters: litellm, bedrock, vertex, vllm, fake)
- [ ] `intelliqx-compute` (ComputeRuntime interface + 3 cloud adapters + local subprocess)
- [ ] `intelliqx-observability` (OTel + LangSmith + structured logging)
- [ ] `intelliqx-agents` (AgentBase + decorators)
- [ ] `intelliqx-tools` (ToolManager + MCP scaffolding)
- [ ] Schemas: `schemas/events/*.json`, `schemas/openapi.yaml`, `schemas/kg/v1.json`
- [ ] GitHub Actions: `.github/workflows/ci.yaml`
- [ ] ADRs: `docs/adr/0001..0011.md`
- [ ] `intelliqx-okf` (OKF bundles, catalog, validator)
- [ ] `docs/architecture/c4.dsl` (System + Container + Component)
- [ ] Unit + contract test suites green

## 0.4 Test/verification criteria

1. **Workspace integrity**: `uv sync` resolves all packages; `uv run pytest tests/unit` 100% green.
2. **Type safety**: `uv run mypy libs` and `uv run mypy agents` exit 0.
3. **Lint clean**: `uv run ruff check .` exits 0.
4. **Event contract**: every event schema validates against sample payloads (positive + negative tests).
5. **Portability smoke**: an agent written against the interfaces runs under all 4 compute/storage adapters (`aws`, `gcp`, `modal`, `local`) in tests.
6. **KG smoke**: ingest 1k nodes/5k edges → 10 representative queries return correct results in <1s.
7. **Vector smoke**: index 10k random vectors (768d) → query top-10 with recall@10 ≥ 0.95 vs brute-force.
8. **Docker Compose validity**: `docker-compose config` (when docker is available) exits 0; lint script passes.
9. **CI pipeline**: `.github/workflows/ci.yaml` lint-validated with `act` or `yamllint`.

## 0.5 Out of scope

- Any concrete agent implementation (deferred to Phases 1–4).
- Cloud deployments (Phases 1, 2, 7).
- Real LLM calls in tests (use `intelliqx-llm.fake`).

## 0.6 Risks

| Risk | Mitigation |
|---|---|
| zvec Python bindings not on PyPI for our Python 3.13 | Pin Python 3.12 in `.python-version`; fallback to Chroma if zvec unavailable |
| DuckDB+Parquet KG doesn't scale to >10M edges | Partition pruning + columnar compression; benchmark in Phase 0 test |
| Modal SDK not usable in CI (no Modal account) | Modal adapter covered by interface contract tests only |