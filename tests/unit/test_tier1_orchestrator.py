"""Tests for Tier 1 Orchestrator Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest
from intelliqx_core.models import RunStatus
from intelliqx_events.bus import get_event_bus
from intelliqx_state.store import get_state_store

from agents import register_all, register_compute_handlers
from agents.tier1.orchestrator import OrchestratorAgent


def _ensure_registered():
    register_all()
    register_compute_handlers()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_runs_single_node():
    _ensure_registered()
    agent = OrchestratorAgent()
    req = InvocationRequest(
        agent_name="orchestrator",
        input={
            "plan_id": "p1",
            "goal_id": "g1",
            "tenant_id": "t1",
            "run_id": "r1",
            "max_parallel": 2,
            "max_retries": 1,
            "nodes": [
                {
                    "node_id": "n1",
                    "agent": "smoke",
                    "inputs": {"marker": "hi"},
                    "depends_on": [],
                    "timeout_seconds": 30,
                }
            ],
        },
        tenant_id="t1",
    )
    out = await agent.invoke(req)
    assert out["status"] == RunStatus.SUCCEEDED.value
    assert len(out["node_results"]) == 1
    assert out["node_results"][0]["status"] == "ok"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_parallel_independent_nodes():
    _ensure_registered()
    agent = OrchestratorAgent()
    req = InvocationRequest(
        agent_name="orchestrator",
        input={
            "plan_id": "p1",
            "goal_id": "g1",
            "tenant_id": "t1",
            "run_id": "r1",
            "nodes": [
                {"node_id": "n1", "agent": "smoke", "inputs": {"marker": "a"}, "depends_on": []},
                {"node_id": "n2", "agent": "smoke", "inputs": {"marker": "b"}, "depends_on": []},
                {"node_id": "n3", "agent": "smoke", "inputs": {"marker": "c"}, "depends_on": []},
            ],
        },
        tenant_id="t1",
    )
    out = await agent.invoke(req)
    assert out["status"] == RunStatus.SUCCEEDED.value
    assert len(out["node_results"]) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_dependency_order():
    _ensure_registered()
    agent = OrchestratorAgent()
    req = InvocationRequest(
        agent_name="orchestrator",
        input={
            "plan_id": "p1",
            "goal_id": "g1",
            "tenant_id": "t1",
            "run_id": "r1",
            "nodes": [
                {"node_id": "n3", "agent": "smoke", "inputs": {}, "depends_on": ["n1", "n2"]},
                {"node_id": "n2", "agent": "smoke", "inputs": {}, "depends_on": ["n1"]},
                {"node_id": "n1", "agent": "smoke", "inputs": {}, "depends_on": []},
            ],
        },
        tenant_id="t1",
    )
    out = await agent.invoke(req)
    results = {r["node_id"]: r for r in out["node_results"]}
    assert results["n1"]["status"] == "ok"
    assert results["n2"]["status"] == "ok"
    assert results["n3"]["status"] == "ok"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_emits_events():
    _ensure_registered()
    bus = get_event_bus()
    received: list[str] = []

    def handler(e):
        received.append(e.detail_type)

    bus.subscribe("run.started", handler)
    bus.subscribe("run.completed", handler)
    bus.subscribe("plan.node.completed", handler)

    agent = OrchestratorAgent()
    req = InvocationRequest(
        agent_name="orchestrator",
        input={
            "plan_id": "p1",
            "goal_id": "g1",
            "tenant_id": "t1",
            "run_id": "r1",
            "nodes": [{"node_id": "n1", "agent": "smoke", "inputs": {}, "depends_on": []}],
        },
        tenant_id="t1",
    )
    await agent.invoke(req)
    assert "RunStarted" in received
    assert "RunCompleted" in received
    assert "PlanNodeCompleted" in received


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_persists_run_status_to_state():
    _ensure_registered()
    agent = OrchestratorAgent()
    req = InvocationRequest(
        agent_name="orchestrator",
        input={
            "plan_id": "p1",
            "goal_id": "g1",
            "tenant_id": "t1",
            "run_id": "r-state",
            "nodes": [{"node_id": "n1", "agent": "smoke", "inputs": {}, "depends_on": []}],
        },
        tenant_id="t1",
    )
    await agent.invoke(req)
    state = get_state_store()
    status = await state.get("run:r-state")
    assert status == b"SUCCEEDED"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_retries_on_failure():
    _ensure_registered()
    # Register a flaky agent that fails the first time and succeeds on the second.
    from intelliqx_compute.runtime import get_compute_runtime

    runtime = get_compute_runtime()
    calls = {"n": 0}

    async def flaky(req):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return {"attempt": calls["n"]}

    runtime.register("flaky", flaky)

    agent = OrchestratorAgent()
    req = InvocationRequest(
        agent_name="orchestrator",
        input={
            "plan_id": "p1",
            "goal_id": "g1",
            "tenant_id": "t1",
            "run_id": "r-retry",
            "max_retries": 2,
            "nodes": [{"node_id": "n1", "agent": "flaky", "inputs": {}, "depends_on": []}],
        },
        tenant_id="t1",
    )
    out = await agent.invoke(req)
    assert out["status"] == RunStatus.SUCCEEDED.value
    assert calls["n"] == 2
    assert out["node_results"][0]["attempts"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_failed_when_retries_exhausted():
    _ensure_registered()
    from intelliqx_compute.runtime import get_compute_runtime

    runtime = get_compute_runtime()

    async def always_fails(req):
        raise RuntimeError("permanent")

    runtime.register("fails", always_fails)

    agent = OrchestratorAgent()
    req = InvocationRequest(
        agent_name="orchestrator",
        input={
            "plan_id": "p1",
            "goal_id": "g1",
            "tenant_id": "t1",
            "run_id": "r-fail",
            "max_retries": 1,
            "nodes": [{"node_id": "n1", "agent": "fails", "inputs": {}, "depends_on": []}],
        },
        tenant_id="t1",
    )
    out = await agent.invoke(req)
    assert out["status"] == RunStatus.FAILED.value
    assert out["node_results"][0]["status"] == "error"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_summary_counts():
    _ensure_registered()
    agent = OrchestratorAgent()
    req = InvocationRequest(
        agent_name="orchestrator",
        input={
            "plan_id": "p1",
            "goal_id": "g1",
            "tenant_id": "t1",
            "run_id": "r1",
            "nodes": [
                {"node_id": "n1", "agent": "smoke", "inputs": {}, "depends_on": []},
                {"node_id": "n2", "agent": "smoke", "inputs": {}, "depends_on": []},
            ],
        },
        tenant_id="t1",
    )
    out = await agent.invoke(req)
    # summary lives in the RunCompleted event; we assert node_results count.
    assert len(out["node_results"]) == 2