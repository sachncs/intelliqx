<p align="center">
  <h1 align="center">intelliqx</h1>
  <p align="center">Autonomous QA Intelligence Platform — agent-native test automation.</p>
  <p align="center">
    <a href="#installation"><img src="https://img.shields.io/badge/python-3.12-blue" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-green" alt="License"></a>
    <a href="https://github.com/sachncs/intelliqx/actions"><img src="https://img.shields.io/github/actions/workflow/status/sachncs/intelliqx/ci.yml?branch=master" alt="CI"></a>
    <a href="https://github.com/sachncs/intelliqx/stargazers"><img src="https://img.shields.io/github/stars/sachncs/intelliqx" alt="Stars"></a>
  </p>
</p>

**intelliqx** is a Python platform that runs 29 specialised agents
that plan, generate, execute, and govern software tests. The same
agent code is portable across process and container boundaries.

```bash
# Install everything (15 libraries + 29 agents + dev tools)
uv sync --all-packages

# Run the full local test pipeline
uv run pytest tests/unit tests/contract tests/integration -q

# Lint + typecheck + dead-code
uv run ruff check .
uv run black --check .
uv run mypy libs agents
uv run vulture libs agents tests .vulture-whitelist

# Start the local infrastructure for adapters
docker compose up -d
```

---

## Features

- **29 Agents Across 4 Categories** — Coordination (Planner,
  Orchestrator, Memory, RAG, Tool Manager), Intelligence
  (Requirements, Code, Risk, Test Design, Test Data, Coverage,
  Critic, Learning, Prompt Mgmt), Execution (Environment, Execution,
  Self-Healing, Failure Analysis, Design Intel, Visual, A11y, Perf,
  Security, Cost Opt), Governance (Observability, Reporting,
  Compliance, Release Readiness).
- **Knowledge Graph on Parquet + DuckDB** — File-based, no managed
  graph DB needed; every node and edge is queryable through SQL.
- **Vector Search via zvec** — Embedded vector store persisted to
  object storage, runs anywhere.
- **OKF Catalog with Hybrid Retrieval** — SQLite + FTS5 + sqlite-vec
  for tenant-scoped full-text + vector search of structured
  documentation.
- **Polymorphic Memory Manager** — One agent entry-point handles
  working, episodic, semantic, and code memories backed by the
  in-process stores.
- **Contract Tests** — Asserts every object-store, state-store, and
  event-bus implementation satisfies the same interface.
- **RBAC + ABAC + Audit Trail** — Tenant-scoped permissions with
  dead-letter queues, human approval workflows, and tamper-evident
  audit records.
- **Zero-Cost Local Dev** — In-memory adapters for events, storage,
  state, vectors, and the LLM client make the entire pipeline
  runnable on a laptop with no external credentials.

---

## Installation

### From source

```bash
git clone https://github.com/sachncs/intelliqx.git
cd intelliqx
uv sync --all-packages       # 15 libraries + 29 agents + dev tools
```

### With Docker

```bash
docker compose up -d         # local adapters
make docker-up
```

**Requirements**: Python 3.12, [uv](https://docs.astral.sh/uv/).

---

## Quick Start

### CLI

```bash
# Run a single agent in-process
uv run python -c "
import asyncio
from agents import register_all
from intelliqx_compute.runtime import InvocationRequest

register_all()
from intelliqx_compute.runtime import get_compute_runtime
from intelliqx_observability.logging import configure_logging, get_logger
req = InvocationRequest(agent_name='smoke', input={'marker': 'hello'}, tenant_id='t1')
configure_logging(json_logs=False, component='quick-start')
get_logger(__name__).info("{}", asyncio.run(get_compute_runtime().invoke(req)))
"

# Run the full local test pipeline
uv run pytest tests/unit tests/contract tests/integration -q

# Start the local infrastructure for adapters
docker compose up -d
```

### Python API

```bash
# Local development (no cloud credentials)
```

```bash
# 1. Install
git clone https://github.com/sachncs/intelliqx.git
cd intelliqx
uv sync --all-packages

# 2. Run the suite (no Docker, no external credentials required)
uv run pytest tests/unit -q

# 3. Try a single agent in-process
uv run python -c "
import asyncio
from agents import register_all
from intelliqx_compute.runtime import InvocationRequest

register_all()
from intelliqx_compute.runtime import get_compute_runtime
from intelliqx_observability.logging import configure_logging, get_logger
req = InvocationRequest(agent_name='smoke', input={'marker': 'hello'}, tenant_id='t1')
configure_logging(json_logs=False, component='quick-start')
get_logger(__name__).info("{}", asyncio.run(get_compute_runtime().invoke(req)))
"
```

### Running against MiniMax

```bash
# Get an API key from https://api.minimax.io
export INTELLIQX_LLM_BACKEND=minimax
export MINIMAX_API_KEY=sk-...
# Optional: override the base URL (default https://api.minimax.io/v1)
export MINIMAX_API_BASE=https://api.minimax.io/v1

uv run python -c "
import asyncio
from intelliqx_llm import get_llm_client
from intelliqx_llm.client import CompletionRequest
from intelliqx_observability.logging import configure_logging, get_logger

async def main():
    client = get_llm_client()
    req = CompletionRequest(
        model='minimax/MiniMax-M2.1',
        messages=[{'role': 'user', 'content': 'Hello!'}],
    )
    resp = await client.complete(req)
    get_logger(__name__).info("{}", resp.content)

configure_logging(json_logs=False, component='llm-example')
asyncio.run(main())
"
```

---

## Configuration

| Setting | Env Variable | Default | Description |
|---------|--------------|---------|-------------|
| LLM backend | `INTELLIQX_LLM_BACKEND` | `fake` | `fake`, or `minimax` |
| Object store | `INTELLIQX_OBJECT_STORE` | `memory` | `memory`, or `fs:/path/to/dir` |
| State backend | `INTELLIQX_STATE_BACKEND` | `memory` | `memory` |
| Event bus backend | `INTELLIQX_EVENT_BUS_BACKEND` | `memory` | `memory` |
| Vector backend | `INTELLIQX_VECTOR_BACKEND` | `memory` | `memory`, `sqlite_vec`, or `zvec` |
| Vector dim | `INTELLIQX_VECTOR_DIM` | `768` | Embedding dimension |
| OTel tracing | `INTELLIQX_OTEL` | `0` | Set to `1` to enable OTel tracing |
| JSON logs | `INTELLIQX_LOGS_JSON` | `0` | Set to `1` for JSON log output |
| MiniMax API key | `MINIMAX_API_KEY` | — | Required for `minimax` backend |

### LLM backend behaviour

| `INTELLIQX_LLM_BACKEND` | Behaviour |
|-------------------------|-----------|
| `fake` (default) | Deterministic hash-based responses (no network) |
| `minimax` | [MiniMax](https://api.minimax.io) via litellm — set `MINIMAX_API_KEY` |

See [`.env.example`](.env.example) for a full template.

---

## API

| Symbol | Type | Description |
|--------|------|-------------|
| `agents.register_all()` | function | Register all 29 agent implementations in the registry |
| `intelliqx_compute.runtime.get_compute_runtime()` | function | Return the active compute runtime |
| `intelliqx_compute.runtime.InvocationRequest` | class | Request payload for agent invocation |
| `intelliqx_llm.get_llm_client()` | function | Return the active LLM client |
| `intelliqx_llm.client.CompletionRequest` | class | LLM completion request (model, messages, …) |
| `intelliqx_llm.client.CompletionResponse` | class | LLM completion response |
| `intelliqx_storage` | package | Object store abstractions (in-memory / filesystem) |
| `intelliqx_events` | package | Event bus abstractions (in-memory) |
| `intelliqx_state` | package | Shared-state abstractions (in-memory) |
| `intelliqx_vector` | package | Vector search backend (zvec / sqlite-vec / in-memory) |
| `intelliqx_kg` | package | Knowledge graph (Parquet + DuckDB) |

---

## Project Structure

```
intelliqx/
├── libs/                14 independent libraries (intelliqx-core, intelliqx-events, ...)
├── agents/              29 agent implementations, grouped by category
│   ├── coordination/    Planner, Orchestrator, Memory, Knowledge/RAG, Tool Manager, Smoke
│   ├── intelligence/    Requirements Intel, Code Intel, Risk, Test Design, Test Data, Coverage, Critic, Learning, Prompt Mgmt
│   ├── execution/       Environment, Design Intel, Execution, Self-Healing, Failure Analysis, Visual Regression, A11y, Perf, Security, Cost Opt
│   └── governance/      Observability, Reporting, Governance & Compliance, Release Readiness
├── schemas/             Event JSON Schemas, KG schema
├── dashboards/          Dashboard definitions
├── prompts/             Prompt templates
├── services/            HTTP / WebSocket entrypoints
├── infra/local/         Local Prometheus / LiteLLM config
├── tests/               unit, integration, contract, e2e
├── docs/                ADRs, architecture, per-phase plans
└── .github/             CI, templates
```

See [`docs/architecture/agent-catalog.md`](docs/architecture/agent-catalog.md)
for the canonical list of every agent, its module path, and its
capabilities. See [`docs/phases/`](docs/phases/) for the phased
implementation plan and [`docs/adr/`](docs/adr/) for Architecture
Decision Records.

---

## Testing

```bash
uv run pytest -q                                # All suites
uv run pytest tests/unit -q                     # Unit only
uv run pytest tests/contract -q                 # Contract tests
uv run pytest tests/integration -q              # Integration
uv run pytest -m e2e -q                         # End-to-end
```

---

## Build

```bash
uv build                                       # workspace wheels + sdist
```

---

## Release

Versions follow [Semantic Versioning](https://semver.org/). Releases are
tracked in [CHANGELOG.md](CHANGELOG.md); breaking changes use the `feat!:` /
`fix!:` Conventional-Commits suffix.

---

## Development

```bash
# Install with dev dependencies (ruff, mypy, black, vulture, pytest)
uv sync --all-packages

# Run tests
uv run pytest -q                                       # All suites
uv run pytest tests/unit -q                            # Unit only
uv run pytest tests/contract -q                        # Contract tests
uv run pytest tests/integration -q                     # Integration
uv run pytest -m e2e -q                                 # End-to-end

# Lint, format, type-check
uv run ruff check .
uv run black .
uv run mypy libs agents

# Dead-code detection
uv run vulture libs agents tests .vulture-whitelist
```

All four tools are wired into CI as separate jobs so a failure in one
no longer masks the others.

### Make targets

```bash
make help               # List all targets
make install            # uv sync --all-packages
make sync               # same
make lint               # ruff check .
make format             # black .
make typecheck          # mypy libs agents
make vulture            # vulture libs agents tests .vulture-whitelist
make test               # pytest
make test-unit          # pytest tests/unit -q
make test-contract      # pytest tests/contract -q
make test-integration   # pytest tests/integration -q
make test-e2e           # pytest tests/e2e -q -m e2e
make run-agent AGENT=execution/execution
make docker-up          # docker compose up -d
make docker-down        # docker compose down
make clean              # rm -rf .venv build dist **/__pycache__ ...
```

### Code style

- **Line length:** 100
- **Formatter:** `black` (enforced in CI)
- **Linter:** `ruff` (selected rules: `E`, `F`, `I`, `B`, `UP`, `SIM`, `RUF`, `T20`)
- **Type checker:** `mypy` (strict-optional, warn-unused-ignores, no-implicit-optional)
- **Naming:** Pydantic models are `PascalCase`; modules and functions are `snake_case`; private members use Python name-mangling (`__name`).
- **Async first:** every public I/O method is `async def`. Blocking SDK calls are offloaded via `asyncio.to_thread`.

### Commit conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add vector indexer abstraction
fix: handle missing OTel SDK in test env
docs: add agent catalog doc
refactor: extract plan templates to a dedicated module
test: add parity test for object-store implementations
chore: update ruff config
```

Breaking changes use the `!` suffix (`feat!:`) and are documented in
[`CHANGELOG.md`](CHANGELOG.md).

---

## Tech Stack

| Category       | Technology                                              |
|----------------|---------------------------------------------------------|
| Language       | Python 3.12                                             |
| Workspace      | [uv](https://docs.astral.sh/uv/) (workspace + lockfile) |
| Models         | [Pydantic v2](https://docs.pydantic.dev/) (strict, frozen) |
| Vector store   | [zvec](https://github.com/alibaba/zvec) (Zilliz embedded) |
| Local vector   | [sqlite-vec](https://github.com/asg017/sqlite-vec)        |
| Graph store    | DuckDB + Parquet on object storage                       |
| State          | in-memory state store                                    |
| Events         | in-process Pub/Sub-style bus                            |
| Storage        | in-memory + filesystem object store                     |
| LLM            | [litellm](https://litellm.ai) (Fake, MiniMax)           |
| Lint           | [ruff](https://docs.astral.sh/ruff/)                    |
| Format         | [black](https://black.readthedocs.io/)                  |
| Type Check     | [mypy](https://mypy-lang.org/) (strict)                 |
| Dead code      | [vulture](https://github.com/jendrikseipp/vulture)      |
| Testing        | [pytest](https://docs.pytest.org/) + pytest-asyncio + pytest-cov |

---

## Roadmap

- **v1.0** — Full agent catalog; observability dashboard.
- **v1.1** — Pluggable vector backend SDK; OKF catalog with hybrid retrieval.
- **v2.0** — Multi-modal agents (visual, a11y, perf); release readiness automation.

## Contributing

We welcome contributions! See [`CONTRIBUTING.md`](CONTRIBUTING.md) for
development setup, the pull request process, coding standards, and test
expectations.

## Code of Conduct

Contributors are expected to follow the
[Contributor Covenant v2.1](CODE_OF_CONDUCT.md).

## Security

Report vulnerabilities to **sachncs@gmail.com** — please do not file
public issues for security-sensitive bugs.

## License

[Apache-2.0](LICENSE) © 2026 Sachin
