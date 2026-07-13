"""Plan templates for goal kinds.

A small catalog of pre-built plan templates, indexed by the goal's
``kind`` field. The Planner Agent consults this table to translate a
:class:`~intelliqx_core.models.Goal` into a list of
:class:`~intelliqx_core.models.PlanNode` records that the Orchestrator
can execute.

The templates intentionally have **no LLM dependency** — they are
deterministic so tests and local dev don't need an LLM provider. A
future revision can add a "goal.kind == 'custom'" branch that asks
an LLM to synthesise a plan on the fly.
"""

from __future__ import annotations

from typing import Any

from intelliqx_core.ids import new_id
from intelliqx_core.models import PlanNode


def plan_for(goal: dict[str, Any], *, available_agents: list[str]) -> list[PlanNode]:
    """Return a plan DAG for the given goal.

    Templates by goal.kind:

    * ``"analyze_prd"`` — requirements → code_intel → test_design
    * ``"run_tests"`` — environment → execution → failure_analysis
    * ``"self_heal_run"`` — execution → self_healing
    * ``"release.readiness"`` — reporting → release_readiness
    * ``"full_qa"`` — requirements → code_intel → test_design →
      environment → execution → failure_analysis → reporting
    * default — single reporting node (degenerate plan; useful for
      smoke tests)

    Each template marks at least one node as ``optional: True`` so
    the Planner's cost-ceiling trim has something to drop when the
    budget is tight.
    """
    kind = goal.get("kind", "")
    nid = lambda: new_id()  # noqa: E731

    if kind == "analyze_prd":
        n1 = nid()
        n2 = nid()
        n3 = nid()
        return [
            PlanNode(node_id=n1, agent="requirements_intel", inputs={"goal": goal}),
            PlanNode(
                node_id=n2,
                agent="code_intel",
                inputs={"goal": goal, "optional": True},
                depends_on=(n1,),
            ),
            PlanNode(node_id=n3, agent="test_design", inputs={"goal": goal}, depends_on=(n2,)),
        ]
    if kind == "run_tests":
        n1 = nid()
        n2 = nid()
        n3 = nid()
        return [
            PlanNode(node_id=n1, agent="environment", inputs={"goal": goal}),
            PlanNode(node_id=n2, agent="execution", inputs={"goal": goal}, depends_on=(n1,)),
            PlanNode(
                node_id=n3,
                agent="failure_analysis",
                inputs={"goal": goal, "optional": True},
                depends_on=(n2,),
            ),
        ]
    if kind == "self_heal_run":
        n1 = nid()
        n2 = nid()
        return [
            PlanNode(node_id=n1, agent="execution", inputs={"goal": goal}),
            PlanNode(
                node_id=n2,
                agent="self_healing",
                inputs={"goal": goal, "optional": True},
                depends_on=(n1,),
            ),
        ]
    if kind == "release.readiness":
        n1 = nid()
        n2 = nid()
        return [
            PlanNode(node_id=n1, agent="reporting", inputs={"goal": goal}),
            PlanNode(
                node_id=n2, agent="release_readiness", inputs={"goal": goal}, depends_on=(n1,)
            ),
        ]
    if kind == "full_qa":
        n = [nid() for _ in range(7)]
        return [
            PlanNode(node_id=n[0], agent="requirements_intel", inputs={"goal": goal}),
            PlanNode(node_id=n[1], agent="code_intel", inputs={"goal": goal}, depends_on=(n[0],)),
            PlanNode(
                node_id=n[2], agent="test_design", inputs={"goal": goal}, depends_on=(n[0], n[1])
            ),
            PlanNode(node_id=n[3], agent="environment", inputs={"goal": goal}, depends_on=(n[2],)),
            PlanNode(node_id=n[4], agent="execution", inputs={"goal": goal}, depends_on=(n[3],)),
            PlanNode(
                node_id=n[5],
                agent="failure_analysis",
                inputs={"goal": goal, "optional": True},
                depends_on=(n[4],),
            ),
            PlanNode(node_id=n[6], agent="reporting", inputs={"goal": goal}, depends_on=(n[5],)),
        ]

    # default: minimal goal-decomposition to plan-generation only
    n1 = nid()
    return [PlanNode(node_id=n1, agent="reporting", inputs={"goal": goal})]
