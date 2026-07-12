# IntelliqX Agent Catalog

This is the canonical list of every agent shipped with the platform,
by tier. Use it as a reference when wiring plans or selecting
capabilities.

| Tier | Agent | Module | META description |
|---|---|---|---|
| 1 | `planner` | `agents.tier1.planner` | Decomposes a Goal into an ExecutionPlan (DAG of agent invocations). |
| 1 | `orchestrator` | `agents.tier1.orchestrator` | Executes a plan DAG, handling retries, parallelism, and audit. |
| 1 | `memory_manager` | `agents.tier1.memory_manager` | Unified memory API: working, episodic, semantic, code memories. |
| 1 | `knowledge_rag` | `agents.tier1.knowledge_rag` | Hybrid retriever: vector + KG + lexical. |
| 1 | `tool_manager` | `agents.tier1.tool_manager` | Universal tool gateway (MCP-compatible). |
| 1 | `smoke` | `agents.tier1.smoke` | Test-only stub agent used for E2E pipeline smoke tests. |
| 2 | `requirements_intel` | `agents.tier2.requirements_intel` | Parses a PRD into structured requirements + traceability matrix. |
| 2 | `code_intel` | `agents.tier2.code_intel` | Builds impact + dependency graphs from code. |
| 2 | `risk_assessment` | `agents.tier2.risk_assessment` | Computes a release risk score from requirements, code impact, and history. |
| 2 | `test_design` | `agents.tier2.test_design` | Generates functional, boundary, negative tests from requirements. |
| 2 | `test_data` | `agents.tier2.test_data` | Generates synthetic test data, privacy-safe by default. |
| 2 | `coverage_analysis` | `agents.tier2.coverage_analysis` | Aggregates requirement, test, and code coverage. |
| 2 | `critic` | `agents.tier2.critic` | Validates agent outputs for correctness, consistency, hallucination. |
| 2 | `learning` | `agents.tier2.learning` | Improves prompts, plans, and healing from history. |
| 2 | `prompt_management` | `agents.tier2.prompt_management` | Manages prompt versions and A/B tests. |
| 3 | `environment` | `agents.tier3.environment` | Provisions an ephemeral test environment. |
| 3 | `design_intel` | `agents.tier3.design_intel` | Extracts semantic UI graph from DOM snapshots. |
| 3 | `execution` | `agents.tier3.execution` | Runs structured test specs against an environment. |
| 3 | `self_healing` | `agents.tier3.self_healing` | Repairs broken selectors by inspecting DOM. |
| 3 | `failure_analysis` | `agents.tier3.failure_analysis` | Classifies test failures (infra / product / flake). |
| 3 | `visual_regression` | `agents.tier3.visual_regression` | Pixel + perceptual diff for visual regression. |
| 3 | `accessibility` | `agents.tier3.accessibility` | WCAG 2.2 AA / keyboard / ARIA / contrast checks. |
| 3 | `performance` | `agents.tier3.performance` | Runs load/stress/spike tests with SLO checks. |
| 3 | `security` | `agents.tier3.security` | SAST, secret detection, dependency scan, DAST. |
| 3 | `cost_optimization` | `agents.tier3.cost_optimization` | Recommends compute right-sizing and scheduling. |
| 4 | `observability` | `agents.tier4.observability` | Aggregates metrics and checks SLA compliance. |
| 4 | `reporting` | `agents.tier4.reporting` | Generates executive + engineering reports. |
| 4 | `governance_compliance` | `agents.tier4.governance_compliance` | RBAC, ABAC, audit trail, human approvals. |
| 4 | `release_readiness` | `agents.tier4.release_readiness` | Produces Go / Conditional Go / No-Go recommendation. |

## How agents are registered

The :func:`agents.register_all` function in `agents/__init__.py` is
the single source of truth for the registry. It imports each
agent class, instantiates a factory closure, and calls
:meth:`AgentRegistry.register` with the agent's :class:`AgentMeta`.
The function is idempotent and safe to call from anywhere.

The :func:`agents.register_compute_handlers` function performs the
same registrations against the
:class:`intelliqx_compute.runtime.InProcessComputeRuntime` so the
Orchestrator can dispatch to any agent by name. Tests call both
functions in a conftest fixture.

## Tier responsibilities

* **Tier 1 — Coordination.** Stateless, single-purpose. The
  Planner emits a DAG; the Orchestrator runs it. They have no
  domain knowledge.
* **Tier 2 — Reasoning.** LLM-using agents that turn requirements,
  code, and history into structured inputs for Tier 3.
* **Tier 3 — Execution.** Side-effecting agents that spin up
  environments, run tests, heal selectors, and measure quality.
* **Tier 4 — Governance.** Cross-cutting agents that observe the
  rest of the platform and produce reports, audits, and release
  decisions.
