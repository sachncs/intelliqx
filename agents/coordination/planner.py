"""Planner Agent (Tier 1).

Transforms a :class:`~intelliqx_core.models.Goal` into a list of
:class:`~intelliqx_core.models.PlanNode` records that form a DAG. The
DAG is validated (no cycles, all dependencies satisfied) and then
trimmed to fit a per-goal cost ceiling. The output includes a
``plan_id`` (a fresh ULID) the Orchestrator can use to look the plan
up.

The planner has **no LLM dependency in v1** — it consults a small
catalog of templates (see :mod:`agents.coordination.templates`) keyed by
``goal.kind``. A future revision can route unknown goal kinds to
an LLM-based plan synthesizer.
"""

from __future__ import annotations

from typing import Any, ClassVar

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import PlanNode
from pydantic import BaseModel, ConfigDict, Field


class PlannerInput(BaseModel):
    """Input to the Planner.

    Attributes:
        goal: The goal dict (typically a serialised
            :class:`~intelliqx_core.models.Goal`).
        tenant_id: The owning tenant.
        available_agents: Optional list of agent names available in
            the runtime; the planner currently ignores this but
            will use it for capability-aware selection in the
            future.
        constraints: Per-goal overrides. Recognised keys:
            ``max_node_timeout_seconds`` (int, default 600) and
            ``cost_ceiling_usd`` (float, default 50.0).
    """

    model_config = ConfigDict(extra="forbid")

    goal: dict[str, Any]
    tenant_id: str
    available_agents: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class PlannerOutput(BaseModel):
    """Output of the Planner.

    Attributes:
        plan_id: Freshly-minted ULID for the plan. Stable across
            the rest of the workflow.
        nodes: Serialised plan nodes, ready for the Orchestrator.
        estimated_cost_usd: Sum of per-node USD estimates.
        estimated_duration_ms: Sum of per-node timeouts (a rough
            upper bound on wall-clock duration).
    """

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    nodes: list[dict[str, Any]]
    estimated_cost_usd: float = 0.0
    estimated_duration_ms: int = 0


class PlannerAgent(AgentBase[PlannerInput, PlannerOutput]):
    """Decomposes a goal into a DAG of agent invocations.

    Pipeline:
        1. ``plan_for`` produces a template-based node list.
        2. Per-node timeout is capped at ``max_node_timeout_seconds``.
        3. The full DAG is validated (Kahn-style cycle check + dep
           existence check).
        4. If the total cost exceeds the ceiling, optional nodes
           (and their transitively-dependent nodes) are dropped.
        5. The trimmed DAG is re-validated (idempotent).
        6. A fresh ``plan_id`` is minted and the nodes are serialised.
    """

    META = AgentMeta(
        name="planner",
        tier=1,
        version="0.1.0",
        description="Decomposes a Goal into an ExecutionPlan (DAG of agent invocations).",
    )
    INPUT_MODEL = PlannerInput
    OUTPUT_MODEL = PlannerOutput

    # Reserved for future plan-template lookup. Currently the
    # templates live in ``agents.coordination.templates`` and are
    # consulted by ``kind`` directly.
    PLAN_TEMPLATES: ClassVar[dict[str, list[PlanNode]]] = {}

    @traced_agent("planner")
    async def run(self, ctx: AgentContext, input: PlannerInput) -> PlannerOutput:
        from intelliqx_core.ids import new_id

        from agents.coordination.templates import plan_for

        nodes = plan_for(input.goal, available_agents=input.available_agents)
        # Apply tenant constraints: per-node timeout cap and cost
        # ceiling.
        timeout_max = int(input.constraints.get("max_node_timeout_seconds", 600))
        cost_ceiling = float(input.constraints.get("cost_ceiling_usd", 50.0))
        for n in nodes:
            n.timeout_seconds = min(n.timeout_seconds, timeout_max)

        # Validate the full DAG *before* any trimming. This catches
        # template bugs (e.g. a typo in a dep) that would otherwise
        # surface only after trimming has lost context.
        _validate_dag(nodes)

        estimated_cost = sum(_node_cost(n) for n in nodes)
        if estimated_cost > cost_ceiling:
            # Trim optional nodes (and their dependents) until
            # within the cost ceiling.
            nodes = _trim_to_cost(nodes, cost_ceiling)
            estimated_cost = sum(_node_cost(n) for n in nodes)

        # Re-validate after trimming (idempotent — DAG is still
        # acyclic, dependencies still satisfied).
        _validate_dag(nodes)

        plan_id = new_id()
        return PlannerOutput(
            plan_id=plan_id,
            nodes=[n.model_dump() for n in nodes],
            estimated_cost_usd=estimated_cost,
            estimated_duration_ms=sum(n.timeout_seconds * 1000 for n in nodes),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _node_cost(n: PlanNode) -> float:
    """Return the estimated USD cost for invoking ``n``.

    The numbers are *estimates* tuned for AWS Bedrock + Lambda
    pricing. They drive cost-ceiling trimming; treat them as rough
    rather than authoritative.
    """
    base = {
        "planner": 0.05,
        "orchestrator": 0.02,
        "memory_manager": 0.01,
        "knowledge_rag": 0.08,
        "tool_manager": 0.02,
        "requirements_intel": 0.20,
        "code_intel": 0.15,
        "test_design": 0.20,
        "critic": 0.10,
        "execution": 0.30,
        "self_healing": 0.10,
        "failure_analysis": 0.10,
        "environment": 0.50,
        "design_intel": 0.08,
        "reporting": 0.05,
        "release_readiness": 0.10,
    }
    return base.get(n.agent, 0.10)


def _trim_to_cost(nodes: list[PlanNode], ceiling: float) -> list[PlanNode]:
    """Drop nodes until the plan's cost fits within ``ceiling``.

    The sort key is ``(optional_first, descending_cost)``: we drop
    optional nodes before required ones, and within each class we
    drop the most expensive first.

    **DAG preservation.** Dropping a node may leave its
    *transitive dependents* with a dangling ``depends_on``. Those
    dependents are dropped too, regardless of their own
    optional/required status. This is intentional: a plan that
    can't afford the upstream work is no better than a plan that
    doesn't include the downstream work.
    """
    sorted_nodes = sorted(
        nodes, key=lambda n: (0 if n.inputs.get("optional") else 1, -_node_cost(n))
    )
    dropped: set[str] = set()
    cur = sum(_node_cost(n) for n in nodes)
    for n in sorted_nodes:
        if cur <= ceiling:
            break
        dropped.add(n.node_id)
        cur -= _node_cost(n)
    _ripple_drop(nodes, dropped)
    return [n for n in nodes if n.node_id not in dropped]


def _ripple_drop(nodes: list[PlanNode], dropped: set[str]) -> None:
    """Drop any node (required or optional) that depends on a dropped node.

    Repeated until stable. See the module docstring of
    :func:`_trim_to_cost` for the rationale.
    """
    changed = True
    while changed:
        changed = False
        for n in nodes:
            if n.node_id in dropped:
                continue
            if any(d in dropped for d in n.depends_on):
                dropped.add(n.node_id)
                changed = True


def _validate_dag(nodes: list[PlanNode]) -> None:
    """Raise :class:`ValueError` if ``nodes`` is not a valid DAG.

    Two checks:
        1. Every ``depends_on`` reference points to a node that
           actually exists.
        2. The graph has no cycles (Kahn's algorithm, O(V + E)).

    The cycle check is implemented with Kahn's topological-sort
    algorithm because it produces a definitive answer in linear
    time, unlike a depth-first search which only proves the
    absence of cycles by traversing everything.
    """
    ids = {n.node_id for n in nodes}
    for n in nodes:
        for d in n.depends_on:
            if d not in ids:
                raise ValueError(f"Node {n.node_id!r} depends on unknown node {d!r}")
    # cycle detection via Kahn's algorithm
    in_degree: dict[str, int] = {n.node_id: 0 for n in nodes}
    adj: dict[str, list[str]] = {n.node_id: [] for n in nodes}
    for n in nodes:
        for d in n.depends_on:
            adj[d].append(n.node_id)
            in_degree[n.node_id] += 1
    queue = [k for k, v in in_degree.items() if v == 0]
    visited = 0
    while queue:
        cur = queue.pop()
        visited += 1
        for nxt in adj[cur]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
    if visited != len(nodes):
        raise ValueError("Plan contains a cycle")
