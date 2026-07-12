# Changelog

All notable changes to **IntelliqX** are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed — Package rename (breaking)

* **Package rename:** The project was formerly named `aqip`. It has been
  renamed to **IntelliqX** for clarity. Import paths, distribution names,
  environment variables, class names, and on-disk resource identifiers
  have all been updated.
  * PyPI / distribution name: `aqip` → `intelliqx`
  * Workspace members: `intelliqx-core`, `intelliqx-agents`,
    `intelliqx-llm`, `intelliqx-events`, … (14 packages)
  * Python import paths: `aqip_core.events` → `intelliqx_core.events`
  * Environment variables: `AQIP_CLOUD` → `INTELLIQX_CLOUD`,
    `AQIP_LLM_BACKEND` → `INTELLIQX_LLM_BACKEND`,
    `AQIP_OBJECT_STORE` → `INTELLIQX_OBJECT_STORE`, etc.
  * Class name: `AQIPError` → `IntelliqxError`
  * CDK / CloudFormation stack names: `aqip-*` → `intelliqx-*`
  * Brand string in docs: "AQIP" → "IntelliqX"

  **Migration:** see `docs/migrations/aqip-to-intelliqx.md`
  (added in a future release) for a step-by-step upgrade guide.

## [0.1.0] — 2026-07-13

First tagged release. Phases 0–5 are complete and verified.

### Added

* **Multi-cloud portability layer.** 14 independent libraries
  (`intelliqx-core`, `intelliqx-events`, `intelliqx-storage`,
  `intelliqx-state`, `intelliqx-vector`, `intelliqx-kg`,
  `intelliqx-llm`, `intelliqx-compute`, `intelliqx-observability`,
  `intelliqx-tools`, `intelliqx-portability`, `intelliqx-tenant`,
  `intelliqx-sdk`, `intelliqx-agents`) implementing single
  abstract interfaces with AWS, GCP, Modal, and local-dev
  adapters.
* **Four-tier agent architecture.**
  * Tier 1 — coordination: Planner, Orchestrator,
    Memory Manager, Knowledge / RAG, Tool Manager.
  * Tier 2 — reasoning: Requirements Intel, Code Intel,
    Risk Assessment, Test Design, Test Data, Coverage
    Analysis, Critic.
  * Tier 3 — execution: Environment, Design Intel, Execution,
    Self-Healing, Failure Analysis.
  * Tier 4 — governance: Observability, Reporting,
    Governance & Compliance.
* **Phases 0–5 complete** (Plans / Tasks in `docs/phases/`).
  Each phase has a comprehensive docstring on every public
  class, function, and method, plus rationale comments on
  algorithms (Kahn's cycle check, cost-ceiling DAG trim,
  Thompson sampling for prompt bandit selection, Uvicorn
  SystemExit workaround, etc.).
* **Local-first dev experience.** 361 tests pass with no
  Docker / cloud-credential dependencies. In-memory adapters
  for events, storage, state, vectors, and the LLM client
  make the entire pipeline runnable on a laptop.
* **Knowledge graph on Parquet + DuckDB.** File-based, no managed
  graph DB needed.
* **Vector search via Zilliz zvec.** Embedded, persisted to
  object storage, runs anywhere.
* **Cross-cloud contract tests.** `tests/cross_cloud/` asserts
  every agent produces identical structured output across
  AWS / GCP / Modal / local profiles.
* **Architecture documentation.** Four files in
  `docs/architecture/` (agent catalog, event taxonomy,
  cost model, multi-cloud matrix).
* **Plan / phase documentation.** Per-phase plans in
  `docs/phases/phase-{0..7}-*.md` and ADR-0001 … ADR-0010
  capture the design decisions.

### Verified

| Surface | Count |
|---|---:|
| Production libs (modules with docstrings) | 14 / 14 |
| Public classes with docstrings | 206 / 206 |
| Public methods / functions with docstrings | 330 / 330 |
| Tests (`uv run pytest`) | 361 passed, 2 skipped¹ |
| Lint (`uv run ruff check .`) | clean |

¹ The two skipped tests are sandbox-rlimit tests that
require POSIX `setrlimit`; macOS does not allow raising CPU/memory
limits, so the tests are skipped on that platform by design.

[Unreleased]: https://github.com/intelliqx/intelliqx/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/intelliqx/intelliqx/releases/tag/v0.1.0
