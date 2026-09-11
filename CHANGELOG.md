# Changelog

All notable changes to **IntelliqX** are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Removed

* **`intelliqx-vector` package** (Zilliz zvec) — no live importers;
  the platform uses `asg017/sqlite-vec` for vector storage. Removed
  zvec references from `intelliqx_storage.store` and the OKF module
  docstring.
* **`intelliqx-llm` package** — OKF now uses Pydaxis-AI's
  `Embedder` directly via `intelliqx_ai.runtime.build_embedder`.
  Updated `tests/conftest.py` to set `INTELLIQX_OPENAI_*` instead
  of the old LLM-backend env vars, and updated `.env.example`,
  `Makefile`, and the README to match.
* **Dead helpers** — `make_run_id()` from `agents.coordination.events`,
  redundant `anyio_backend` fixture from `tests/conftest`, redundant
  `TenantContext`/`AgentContext` re-imports from
  `intelliqx_agents.base.invoke()`, redundant `struct` re-import from
  `intelliqx_okf.catalog`, and unused `EdgeType.MESSAGE` enum member
  from `intelliqx_graph.models`.

### Changed

* **Service auth hardening.** `intelliqx-service` refuses to start
  unless `INTELLIQX_API_TOKEN` is set to a value of at least 32
  characters; the previous `dev-token-change-me` fallback shipped a
  publicly known bearer token.
* **Compose file credentials.** MinIO and Grafana now read
  `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, and
  `GF_SECURITY_ADMIN_PASSWORD` from `.env.compose`; the file
  documents the variables and uses `${VAR:?}` required-variable
  expansion so `docker compose` fails loudly if they are unset.
* **Docs alignment.** `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`,
  and the architecture docs now agree on the agent count (28),
  the workspace-member count (15 libs + agents + tests = 17), and
  the LLM backend (single OpenAI-compatible path via
  `intelliqx_ai.runtime`). `agent-catalog.md` describes the
  flat `ROLE_TABLE` registry; references to `agents.coordination.*`,
  `agents.intelligence.*`, `agents.execution.*`,
  `agents.governance.*` were replaced with the real modules.
* **CI formatter.** `Makefile` and `ci.yml` now both use
  `ruff format`; the legacy `[tool.black]` config and the
  `black` dev dependency were removed.
* **Coverage gate enforced.** A new `coverage` CI job runs the unit
  + contract suites under `coverage` and fails if the threshold
  drops below 70%.

### Added

* **ADR-0012** — documents the single OpenAI-compatible chat path
  through `intelliqx_ai.runtime` (renamed from the stale litellm
  ADR).
* **`/metrics` endpoint** — `intelliqx-service` exposes a
  Prometheus text-exposition endpoint that renders the
  in-process `MetricsRegistry`.
* **SECURITY.md cross-links** — the README and CONTRIBUTING.md
  point at SECURITY.md for vulnerability disclosures.
* **Issue / PR templates** — `.github/ISSUE_TEMPLATE/security.yml`
  and an expanded `.github/PULL_REQUEST_TEMPLATE.md` listing the
  seven CI jobs.
* **Coverage artifact** — the coverage job uploads `coverage.xml`
  to the run.

## [0.1.0] — 2026-07-13

First tagged release. Phases 0 and 3–6 are complete and verified.

### Added

* **Four-category agent architecture.**
  * Coordination — Planner, Orchestrator,
    Memory Manager, Knowledge / RAG, Tool Manager.
  * Intelligence — Requirements Intel, Code Intel,
    Risk Assessment, Test Design, Test Data, Coverage
    Analysis, Critic, Learning, Prompt Management.
  * Execution — Environment, Design Intel, Execution,
    Self-Healing, Failure Analysis, Visual Regression,
    Accessibility, Performance, Security, Cost Optimization.
  * Governance — Observability, Reporting,
    Governance & Compliance, Release Readiness.
* **Phases 0 and 3–6 complete** (Plans / Tasks in `docs/phases/`).
  Each phase has a comprehensive docstring on every public
  class, function, and method, plus rationale comments on
  algorithms (Kahn's cycle check, cost-ceiling DAG trim,
  Thompson sampling for prompt bandit selection, Uvicorn
  SystemExit workaround, etc.).
* **Local-first dev experience.** In-memory adapters
  for events, storage, state, vectors, and the LLM client
  make the entire pipeline runnable on a laptop with no
  external credentials.
* **Knowledge graph on Parquet + DuckDB.** File-based, no managed
  graph DB needed.
* **Vector search via Zilliz zvec.** Embedded, persisted to
  object storage, runs anywhere.
* **Architecture documentation.** Three files in
  `docs/architecture/` (agent catalog, event taxonomy,
  cost model).
* **Plan / phase documentation.** Per-phase plans in
  `docs/phases/phase-{0,3..6}.md` and ADR-0001, ADR-0003–0012
  capture the design decisions.

[Unreleased]: https://github.com/sachncs/intelliqx/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sachncs/intelliqx/releases/tag/v0.1.0
