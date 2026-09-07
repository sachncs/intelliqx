# IntelliqX Agent Catalog

This is the canonical list of every agent shipped with the platform,
by category. Use it as a reference when wiring plans or selecting
capabilities.

| Category | Agent | Module | META description |
|---|---|---|---|
| coordination | `planner` | `agents.coordination.planner` | Decomposes a Goal into an ExecutionPlan (DAG of agent invocations). |
| coordination | `orchestrator` | `agents.coordination.orchestrator` | Executes a plan DAG, handling retries, parallelism, and audit. |
| coordination | `memory_manager` | `agents.coordination.memory_manager` | Unified memory API: working, episodic, semantic, code memories. |
| coordination | `knowledge_rag` | `agents.coordination.knowledge_rag` | Hybrid four-source retriever: vector + KG + lexical + OKF catalog (RRF). |
| coordination | `tool_manager` | `agents.coordination.tool_manager` | Universal tool gateway (MCP-compatible). |
| coordination | `smoke` | `agents.coordination.smoke` | Test-only stub agent used for E2E pipeline smoke tests. |
| intelligence | `requirements_intel` | `agents.intelligence.requirements_intel` | Parses a PRD into structured requirements + traceability matrix. |
| intelligence | `code_intel` | `agents.intelligence.code_intel` | Builds impact + dependency graphs from code. |
| intelligence | `risk_assessment` | `agents.intelligence.risk_assessment` | Computes a release risk score from requirements, code impact, and history. |
| intelligence | `test_design` | `agents.intelligence.test_design` | Generates functional, boundary, negative tests from requirements. |
| intelligence | `test_data` | `agents.intelligence.test_data` | Generates synthetic test data, privacy-safe by default. |
| intelligence | `coverage_analysis` | `agents.intelligence.coverage_analysis` | Aggregates requirement, test, and code coverage. |
| intelligence | `critic` | `agents.intelligence.critic` | Validates agent outputs for correctness, consistency, hallucination. |
| intelligence | `learning` | `agents.intelligence.learning` | Improves prompts, plans, and healing from history. |
| intelligence | `prompt_management` | `agents.intelligence.prompt_management` | Manages prompt versions and A/B tests. |
| execution | `environment` | `agents.execution.environment` | Provisions an ephemeral test environment. |
| execution | `design_intel` | `agents.execution.design_intel` | Extracts semantic UI graph from DOM snapshots. |
| execution | `execution` | `agents.execution.execution` | Runs structured test specs against an environment. |
| execution | `self_healing` | `agents.execution.self_healing` | Repairs broken selectors by inspecting DOM. |
| execution | `failure_analysis` | `agents.execution.failure_analysis` | Classifies test failures (infra / product / flake). |
| execution | `visual_regression` | `agents.execution.visual_regression` | Pixel + perceptual diff for visual regression. |
| execution | `accessibility` | `agents.execution.accessibility` | WCAG 2.2 AA / keyboard / ARIA / contrast checks. |
| execution | `performance` | `agents.execution.performance` | Runs load/stress/spike tests with SLO checks. |
| execution | `security` | `agents.execution.security` | SAST, secret detection, dependency scan, DAST. |
| execution | `cost_optimization` | `agents.execution.cost_optimization` | Recommends compute right-sizing and scheduling. |
| governance | `observability` | `agents.governance.observability` | Aggregates metrics and checks SLA compliance. |
| governance | `reporting` | `agents.governance.reporting` | Generates executive + engineering reports. |
| governance | `governance_compliance` | `agents.governance.governance_compliance` | RBAC, ABAC, audit trail, human approvals. |
| governance | `release_readiness` | `agents.governance.release_readiness` | Produces Go / Conditional Go / No-Go recommendation. |

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

## Category responsibilities

* **Coordination.** Stateless, single-purpose. The
  Planner emits a DAG; the Orchestrator runs it. They have no
  domain knowledge.
* **Intelligence.** LLM-using agents that turn requirements,
  code, and history into structured inputs for Execution.
* **Execution.** Side-effecting agents that spin up
  environments, run tests, heal selectors, and measure quality.
* **Governance.** Cross-cutting agents that observe the
  rest of the platform and produce reports, audits, and release
  decisions.