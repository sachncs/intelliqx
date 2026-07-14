# Changelog

All notable changes to **IntelliqX** are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

* **MiniMax LLM adapter** — new
  `intelliqx_llm.minimax.MiniMaxLLMClient` routes chat and embed
  through
  [`litellm`](https://docs.litellm.ai/docs/providers/minimax).
  Set `INTELLIQX_LLM_BACKEND=minimax` plus `MINIMAX_API_KEY` (and
  optional `MINIMAX_API_BASE`) to use it. Graceful-degradation
  pattern matches the existing cloud adapters: a missing SDK or
  key produces a `[minimax-fallback:<sha256>...]` response so
  CI on a laptop with no cloud credentials keeps working.
* **`intelliqx-llm-smoke` console script** — installed by
  `intelliqx-llm`; runs a one-shot `complete()` (or `embed()`
  with `--embed`) against the configured backend and prints
  the response plus per-call latency. Exits 0 on success, 1
  on any failure (including an unknown `INTELLIQX_LLM_BACKEND`).
* **ADR-0012** — documents the decision to standardise on
  `litellm` as the provider-agnostic SDK and the trade-offs
  (large dependency, broad-except catch, smoke-CLI pattern).

### Changed — Quality hardening (comprehensive refactor)

This release contains a top-to-bottom quality pass: every commit on
the `feat/okf-sqlitevec-retrieval` branch is reviewable in isolation
and the final merge is squash-clean.

* **Formatting:** `ruff format` applied repo-wide (94 files reformatted).
* **Type safety:** 83 mypy errors resolved across all 15 libraries.
  Optional typing added to cloud client fields; 14 previously-unguarded
  state-adapter methods now raise `RuntimeError` cleanly when the SDK is
  absent instead of `AttributeError` on `None`.
* **Abstract base classes:** `ObjectStore`, `StateStore`, `ComputeRuntime`,
  `EventBus`, and `AgentBase` now inherit `abc.ABC` and use
  `@abstractmethod` — missing implementations are caught at class
  instantiation, not method-call time.
* **Agent category rename:** `tier1`/`tier2`/`tier3`/`tier4` directories are
  renamed `coordination`/`intelligence`/`execution`/`governance`.
  The numeric `AgentMeta.tier` field is replaced by `AgentMeta.category`
  (an `AgentCategory` enum: `coordination`, `intelligence`, `execution`,
  `governance`). `AgentRef` and `AgentManifest` follow the same
  renaming; ordering is preserved by the enum declaration order.
  The descriptive names make the architecture self-documenting and
  make every reference in code, tests, and docs read like English
  instead of an opaque integer.
* **Cloud adapter hardening:** bare `except Exception` in `_try_init`
  narrowed to `(ImportError, OSError)` across all 13 cloud adapters so
  configuration errors are loud while SDK-absence is silent; GCP compute
  `_available` now reflects actual httpx availability.
* **Real implementations for Vertex/Bedrock:** `VertexLLMClient.complete()`
  and `.embed()` and `BedrockLLMClient.embed()` now make real API calls
  instead of raising `NotImplementedError`. A shared `deterministic_embedding()`
  helper consolidates the hash-based fallback that was duplicated across
  all three LLM adapters.
* **Cloud SDK stubs:** proper type stubs and `# type: ignore` comments
  added for opentelemetry, ulid, duckdb, pyarrow, sqlite_vec, yaml.
* **Naming consistency:** `ToolRegistry.list()` renamed to `list_tools()`
  to avoid shadowing the builtin. All agent input/output models
  standardised on `{Agent}Input` / `{Agent}Output` (previously three
  different naming conventions across 29 agents).
* **Singleton naming:** `_STORE_SINGLETON`, `_BUS_SINGLETON`,
  `_KG_SINGLETON`, and `_INSTANCE` unified to `_SINGLETON` across
  all 15 libraries.
* **Error handling documentation:** every cloud adapter documents its
  `_try_init` / `_available` / `_require` pattern in its module
  docstring — explains why each adapter catches `(ImportError, OSError)`
  specifically and what behavior callers can expect when the SDK is
  absent.

### Added

* **OKF catalog with hybrid retrieval.** `intelliqx-okf` adds a
  SQLite-backed catalog (`OKFCatalog`) that combines FTS5 full-text
  search, sqlite-vec vector similarity, and typed metadata
  (concept type, tags, timestamp) into a single query. Retrieval
  uses dual-candidate reciprocal-rank fusion (RRF) for robust
  merging of keyword and semantic results.
* **Tenant-scoped catalog.** The catalog schema uses a composite
  primary key `(concept_id, tenant_id)`, enabling multiple tenants
  to share one SQLite file without cross-contamination.
* **OKF validator.** `validate_concept()` and `validate_bundle()`
  check that OKF frontmatter and body structure conform to the
  OKF v0.1 spec.
* **OKF bootstrap.** `bootstrap_okf_retrieval()` loads tenant-
  scoped bundles, builds the catalog, batch-embeds concepts, and
  stores embeddings in both the catalog and the global vector
  index.
* **SqliteVecIndex.** `intelliqx-vector` gains a `SqliteVecIndex`
  implementation using the `sqlite-vec` extension for local
  vector search with cosine similarity.
* **Knowledge/RAG four-source pipeline.** The `KnowledgeRAGAgent`
  now fuses four sources (vector, KG, lexical, OKF) via weighted
  reciprocal-rank fusion with configurable per-source weights.

### Changed — Package rename (breaking)

* **Package rename:** The project was formerly named `aqip`. It has been
  renamed to **IntelliqX** for clarity. Import paths, distribution names,
  environment variables, class names, and on-disk resource identifiers
  have all been updated.
  * PyPI / distribution name: `aqip` → `intelliqx`
  * Workspace members: `intelliqx-core`, `intelliqx-agents`,
    `intelliqx-llm`, `intelliqx-events`, … (15 packages)
  * Python import paths: `aqip_core.events` → `intelliqx_core.events`
  * Environment variables: `AQIP_CLOUD` → `INTELLIQX_CLOUD`,
    `AQIP_LLM_BACKEND` → `INTELLIQX_LLM_BACKEND`,
    `AQIP_OBJECT_STORE` → `INTELLIQX_OBJECT_STORE`, etc.
  * Class name: `AQIPError` → `IntelliqxError`
  * CDK / CloudFormation stack names: `aqip-*` → `intelliqx-*`
  * Brand string in docs: "AQIP" → "IntelliqX"

  **Migration:** see the package rename section above for the
  full mapping of old names to new names.

## [0.1.0] — 2026-07-13

First tagged release. Phases 0–1 are complete and verified; Phases 2–7 are planned.

### Added

* **Multi-cloud portability layer.**   15 independent libraries
  (`intelliqx-core`, `intelliqx-events`, `intelliqx-storage`,
  `intelliqx-state`, `intelliqx-vector`, `intelliqx-kg`,
  `intelliqx-llm`, `intelliqx-compute`, `intelliqx-observability`,
  `intelliqx-tools`, `intelliqx-portability`, `intelliqx-tenant`,
  `intelliqx-sdk`, `intelliqx-agents`) implementing single
  abstract interfaces with AWS, GCP, Modal, and local-dev
  adapters.
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
* **Phases 0–5 complete** (Plans / Tasks in `docs/phases/`).
  Each phase has a comprehensive docstring on every public
  class, function, and method, plus rationale comments on
  algorithms (Kahn's cycle check, cost-ceiling DAG trim,
  Thompson sampling for prompt bandit selection, Uvicorn
  SystemExit workaround, etc.).
* **Local-first dev experience.** 354 tests pass with no
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
  `docs/phases/phase-{0..7}-*.md` and ADR-0001 … ADR-0011
  capture the design decisions.

### Verified

| Surface | Count |
|---|---:|
| Production libs (modules with docstrings) | 15 / 15 |
| Public classes with docstrings | 206 / 206 |
| Public methods / functions with docstrings | 481 / 481 |
| Tests (`uv run pytest`) | 354 passed, 2 skipped¹ |
| Lint (`uv run ruff check .`) | clean |

¹ The two skipped tests are sandbox-rlimit tests that
require POSIX `setrlimit`; macOS does not allow raising CPU/memory
limits, so the tests are skipped on that platform by design.

[Unreleased]: https://github.com/sachncs/intelliqx/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sachncs/intelliqx/releases/tag/v0.1.0
