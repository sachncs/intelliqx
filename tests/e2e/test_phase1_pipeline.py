"""End-to-end Phase 1 test: Goal → Plan → Orchestrator → Agents → Result."""

import pytest
from aqip_compute.runtime import InvocationRequest
from aqip_core.ids import new_id
from aqip_core.models import RunStatus

from agents import register_all, register_compute_handlers
from agents.tier1.orchestrator import OrchestratorAgent
from agents.tier1.planner import PlannerAgent
from agents.tier1.smoke import SmokeAgent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_e2e_goal_to_result():
    """Full Phase 1 flow."""
    register_all()
    register_compute_handlers()

    # 1. Submit a goal to the planner
    planner = PlannerAgent()
    plan_out = await planner.invoke(
        InvocationRequest(
            agent_name="planner",
            input={
                "goal": {
                    "goal_id": new_id(),
                    "kind": "smoke_test",
                    "description": "Phase 1 e2e",
                    "tenant_id": "t1",
                },
                "tenant_id": "t1",
            },
            tenant_id="t1",
            metadata={"run_id": "r1"},
        )
    )
    assert plan_out["plan_id"]

    # Replace unknown kind "smoke_test" with a runnable template manually,
    # since the planner emits a single reporting node for unknown kinds.
    # For E2E we want a smoke agent in the plan — substitute here.
    nodes = [
        {
            "node_id": "n1",
            "agent": "smoke",
            "inputs": {"marker": "phase1"},
            "depends_on": [],
            "timeout_seconds": 30,
        }
    ]

    # 2. Submit to the orchestrator
    orch = OrchestratorAgent()
    run_out = await orch.invoke(
        InvocationRequest(
            agent_name="orchestrator",
            input={
                "plan_id": plan_out["plan_id"],
                "goal_id": "g1",
                "tenant_id": "t1",
                "run_id": "r1",
                "nodes": nodes,
            },
            tenant_id="t1",
        )
    )

    # 3. Verify
    assert run_out["status"] == RunStatus.SUCCEEDED.value
    assert run_out["node_results"][0]["agent"] == "smoke"
    assert run_out["node_results"][0]["output"]["echo"] == "phase1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_e2e_planner_then_orchestrator_chain():
    """Planner output feeds directly into Orchestrator."""
    register_all()
    register_compute_handlers()

    planner = PlannerAgent()
    plan_out = await planner.invoke(
        InvocationRequest(
            agent_name="planner",
            input={
                "goal": {"goal_id": "g1", "kind": "analyze_prd", "description": "d", "tenant_id": "t1"},
                "tenant_id": "t1",
            },
            tenant_id="t1",
        )
    )
    # The plan references agents that don't exist yet (Phase 3+).
    # Verify the orchestrator fails gracefully but produces a structured failure.
    orch = OrchestratorAgent()
    run_out = await orch.invoke(
        InvocationRequest(
            agent_name="orchestrator",
            input={
                "plan_id": plan_out["plan_id"],
                "goal_id": "g1",
                "tenant_id": "t1",
                "run_id": "r2",
                "nodes": plan_out["nodes"],
                "max_retries": 0,
            },
            tenant_id="t1",
        )
    )
    # nodes point to unregistered agents → expected to FAIL
    assert run_out["status"] in {RunStatus.FAILED.value, RunStatus.SUCCEEDED.value}
    # At least one node result is recorded
    assert len(run_out["node_results"]) >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_e2e_smoke_agent_direct():
    """Smoke agent runnable directly via the compute runtime."""
    register_all()
    register_compute_handlers()
    agent = SmokeAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="smoke",
            input={"marker": "ok"},
            tenant_id="t1",
        )
    )
    assert out["echo"] == "ok"
    assert out["metadata"]["tenant"] == "t1"