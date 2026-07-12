"""Phase 4 E2E: full Goal → Plan → Execution → Self-Healing → Failure Analysis."""

import pytest
from aqip_compute.runtime import InvocationRequest
from aqip_core.models import RunStatus

from agents import register_all, register_compute_handlers
from agents.tier1.orchestrator import OrchestratorAgent
from agents.tier1.planner import PlannerAgent
from agents.tier3.environment import EnvironmentAgent
from agents.tier3.execution import TestSpec, TestStep
from agents.tier3.self_healing import SelfHealingAgent


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_pipeline_goal_to_failure_analysis():
    """Goal → Plan → Orchestrator → Environment → Execution → Failure Analysis."""
    register_all()
    register_compute_handlers()

    # 1. Provision an environment
    env_agent = EnvironmentAgent()
    env_out = await env_agent.invoke(
        InvocationRequest(
            agent_name="environment",
            input={"port": 0, "health_path": "/health", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert env_out["ready"]
    base_url = env_out["base_url"]

    # 2. Build a plan with environment → execution → failure_analysis
    orch = OrchestratorAgent()
    run_out = await orch.invoke(
        InvocationRequest(
            agent_name="orchestrator",
            input={
                "plan_id": "p1",
                "goal_id": "g1",
                "tenant_id": "t1",
                "run_id": "r-pipeline",
                "nodes": [
                    {
                        "node_id": "n1",
                        "agent": "execution",
                        "inputs": {
                            "base_url": base_url,
                            "tenant_id": "t1",
                            "tests": [
                                TestSpec(
                                    name="health",
                                    steps=[TestStep(action="get", path="/health", expected_status=200)],
                                ).model_dump(),
                                TestSpec(
                                    name="bad_status",
                                    steps=[TestStep(action="get", path="/health", expected_status=404)],
                                ).model_dump(),
                            ],
                        },
                        "depends_on": [],
                        "timeout_seconds": 60,
                    },
                    {
                        "node_id": "n2",
                        "agent": "failure_analysis",
                        "inputs": {
                            "error": "got 500 server error",
                            "retry_count": 0,
                            "history": [],
                        },
                        "depends_on": ["n1"],
                        "timeout_seconds": 30,
                    },
                ],
            },
            tenant_id="t1",
        )
    )
    assert run_out["status"] == RunStatus.SUCCEEDED.value
    assert len(run_out["node_results"]) == 2


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_self_healing_against_reference_app_html():
    """Design Intelligence + Self-Healing work on the reference app HTML."""
    import httpx

    register_all()
    register_compute_handlers()

    env_agent = EnvironmentAgent()
    env_out = await env_agent.invoke(
        InvocationRequest(
            agent_name="environment",
            input={"port": 0, "health_path": "/health", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    base_url = env_out["base_url"]

    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{base_url}/page")
    assert r.status_code == 200

    healing_agent = SelfHealingAgent()
    heal_out = await healing_agent.invoke(
        InvocationRequest(
            agent_name="self_healing",
            input={
                "failed_selector": "#missing-id",
                "dom_html": r.text,
                "min_confidence": 0.7,
            },
            tenant_id="t1",
        )
    )
    assert heal_out["healed"]
    assert heal_out["applied_selector"] is not None


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_orchestrator_with_planner_for_run_tests():
    """Planner (run_tests) → Orchestrator → Environment → Execution → Failure Analysis."""
    register_all()
    register_compute_handlers()
    planner = PlannerAgent()
    plan = await planner.invoke(
        InvocationRequest(
            agent_name="planner",
            input={
                "goal": {"goal_id": "g1", "kind": "run_tests", "description": "d", "tenant_id": "t1"},
                "tenant_id": "t1",
            },
            tenant_id="t1",
        )
    )
    # Substitute environment's inputs to point at a real env
    env_agent = EnvironmentAgent()
    env_out = await env_agent.invoke(
        InvocationRequest(
            agent_name="environment",
            input={"port": 0, "health_path": "/health", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    base_url = env_out["base_url"]

    # Override env node inputs to skip URL resolution (we already have base_url)
    nodes = []
    for n in plan["nodes"]:
        if n["agent"] == "environment":
            n["inputs"] = {"port": 0, "health_path": "/health", "tenant_id": "t1"}
        elif n["agent"] == "execution":
            n["inputs"] = {
                "base_url": base_url,
                "tenant_id": "t1",
                "tests": [
                    TestSpec(
                        name="health",
                        steps=[TestStep(action="get", path="/health", expected_status=200)],
                    ).model_dump(),
                ],
            }
        nodes.append(n)

    orch = OrchestratorAgent()
    run_out = await orch.invoke(
        InvocationRequest(
            agent_name="orchestrator",
            input={
                "plan_id": plan["plan_id"],
                "goal_id": "g1",
                "tenant_id": "t1",
                "run_id": "r-planner-pipeline",
                "nodes": nodes,
            },
            tenant_id="t1",
        )
    )
    # At least the environment and execution nodes ran
    agents_executed = {r["agent"] for r in run_out["node_results"]}
    assert "environment" in agents_executed
    assert "execution" in agents_executed