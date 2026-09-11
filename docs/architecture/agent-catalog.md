# IntelliqX Agent Catalog

This is the canonical list of every agent shipped with the platform,
by category. Use it as a reference when wiring plans or selecting
capabilities.

The agent catalog is a single flat `ROLE_TABLE` tuple in
`agents/ai/roles.py`. Each row of the table is a `RoleSpec` whose
`name`, `category`, `instructions`, and `output_model` describe one
role. The `AgentCategory` enum (`coordination`, `intelligence`,
`execution`, `governance`) groups the rows for documentation but the
runtime treats every row uniformly.

| Category | Agent | RoleSpec entry |
|---|---|---|
| coordination | `planner` | `ROLE_TABLE[*].name == "planner"` |
| coordination | `orchestrator` | `ROLE_TABLE[*].name == "orchestrator"` |
| coordination | `knowledge_rag` | `ROLE_TABLE[*].name == "knowledge_rag"` |
| coordination | `tool_manager` | `ROLE_TABLE[*].name == "tool_manager"` |
| coordination | `smoke` | `ROLE_TABLE[*].name == "smoke"` |
| intelligence | `requirements_intel` | `ROLE_TABLE[*].name == "requirements_intel"` |
| intelligence | `code_intel` | `ROLE_TABLE[*].name == "code_intel"` |
| intelligence | `risk_assessment` | `ROLE_TABLE[*].name == "risk_assessment"` |
| intelligence | `test_design` | `ROLE_TABLE[*].name == "test_design"` |
| intelligence | `test_data` | `ROLE_TABLE[*].name == "test_data"` |
| intelligence | `coverage_analysis` | `ROLE_TABLE[*].name == "coverage_analysis"` |
| intelligence | `critic` | `ROLE_TABLE[*].name == "critic"` |
| intelligence | `learning` | `ROLE_TABLE[*].name == "learning"` |
| intelligence | `prompt_management` | `ROLE_TABLE[*].name == "prompt_management"` |
| execution | `environment` | `ROLE_TABLE[*].name == "environment"` |
| execution | `design_intel` | `ROLE_TABLE[*].name == "design_intel"` |
| execution | `execution` | `ROLE_TABLE[*].name == "execution"` |
| execution | `self_healing` | `ROLE_TABLE[*].name == "self_healing"` |
| execution | `failure_analysis` | `ROLE_TABLE[*].name == "failure_analysis"` |
| execution | `visual_regression` | `ROLE_TABLE[*].name == "visual_regression"` |
| execution | `accessibility` | `ROLE_TABLE[*].name == "accessibility"` |
| execution | `performance` | `ROLE_TABLE[*].name == "performance"` |
| execution | `security` | `ROLE_TABLE[*].name == "security"` |
| execution | `cost_optimization` | `ROLE_TABLE[*].name == "cost_optimization"` |
| governance | `observability` | `ROLE_TABLE[*].name == "observability"` |
| governance | `reporting` | `ROLE_TABLE[*].name == "reporting"` |
| governance | `governance_compliance` | `ROLE_TABLE[*].name == "governance_compliance"` |
| governance | `release_readiness` | `ROLE_TABLE[*].name == "release_readiness"` |

## How agents are registered

The :func:`agents.register_all` function in `agents/__init__.py` is
the single source of truth for the registry. It iterates the
`ROLE_TABLE` in `agents/ai/roles.py`, builds an `AgentMeta` for each
row, and calls :meth:`AgentRegistry.register` with the agent's
factory closure. The function is idempotent and safe to call from
anywhere.

The :func:`agents.register_compute_handlers` function performs the
same registrations against the
:class:`intelliqx_compute.runtime.InProcessComputeRuntime` so the
Orchestrator can dispatch to any agent by name. Tests call both
functions in a conftest fixture.

## Adding a new agent

1. Add a new `RoleSpec` row to `ROLE_TABLE` in `agents/ai/roles.py`
   using the appropriate `category` value.
2. Add a unit test in `tests/unit/test_agent_roles.py` that
   constructs the agent and asserts the configured output type.
3. Add the row to the table above.
4. Open a PR — the test and catalog entry are required for merge.

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