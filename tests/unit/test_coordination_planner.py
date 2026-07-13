"""Tests for  Planner Agent."""

import pytest
from intelliqx_agents.registry import get_agent_registry
from intelliqx_compute.runtime import InvocationRequest
from intelliqx_core.models import PlanNode

from agents import register_all, register_compute_handlers
from agents.coordination.planner import PlannerAgent, _trim_to_cost, _validate_dag
from agents.coordination.templates import plan_for


@pytest.mark.unit
@pytest.mark.asyncio
async def test_planner_run_for_analyze_prd():
    register_all()
    register_compute_handlers()
    agent = PlannerAgent()
    req = InvocationRequest(
        agent_name="planner",
        input={
            "goal": {"goal_id": "g1", "kind": "analyze_prd", "description": "d", "tenant_id": "t1"},
            "tenant_id": "t1",
            "available_agents": ["requirements_intel", "code_intel", "test_design"],
            "constraints": {},
        },
        tenant_id="t1",
        metadata={"run_id": "r1"},
    )
    out = await agent.invoke(req)
    assert out["plan_id"]
    assert len(out["nodes"]) >= 3
    agent_names = {n["agent"] for n in out["nodes"]}
    assert "requirements_intel" in agent_names
    assert "test_design" in agent_names


@pytest.mark.unit
@pytest.mark.asyncio
async def test_planner_run_for_run_tests():
    register_all()
    register_compute_handlers()
    agent = PlannerAgent()
    req = InvocationRequest(
        agent_name="planner",
        input={
            "goal": {"goal_id": "g1", "kind": "run_tests", "description": "d", "tenant_id": "t1"},
            "tenant_id": "t1",
        },
        tenant_id="t1",
    )
    out = await agent.invoke(req)
    agent_names = {n["agent"] for n in out["nodes"]}
    assert "environment" in agent_names
    assert "execution" in agent_names


@pytest.mark.unit
@pytest.mark.asyncio
async def test_planner_cost_ceiling_trims_optional_nodes():
    register_all()
    register_compute_handlers()
    agent = PlannerAgent()
    # Tight ceiling forces trimming.
    req = InvocationRequest(
        agent_name="planner",
        input={
            "goal": {"goal_id": "g1", "kind": "full_qa", "description": "d", "tenant_id": "t1"},
            "tenant_id": "t1",
            "constraints": {"cost_ceiling_usd": 0.30},
        },
        tenant_id="t1",
    )
    out = await agent.invoke(req)
    # We should still have required nodes, optional may be trimmed.
    assert out["estimated_cost_usd"] <= 0.30
    # DAG must still be valid
    kept_ids = {n["node_id"] for n in out["nodes"]}
    for n in out["nodes"]:
        for d in n.get("depends_on", []):
            assert d in kept_ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_planner_node_timeout_capped():
    register_all()
    register_compute_handlers()
    agent = PlannerAgent()
    req = InvocationRequest(
        agent_name="planner",
        input={
            "goal": {"goal_id": "g1", "kind": "run_tests", "description": "d", "tenant_id": "t1"},
            "tenant_id": "t1",
            "constraints": {"max_node_timeout_seconds": 5},
        },
        tenant_id="t1",
    )
    out = await agent.invoke(req)
    for n in out["nodes"]:
        assert n["timeout_seconds"] <= 5


@pytest.mark.unit
def test_plan_for_unknown_kind_returns_minimal_plan():
    nodes = plan_for({"kind": "totally_unknown"}, available_agents=[])
    assert len(nodes) >= 1
    assert nodes[0].agent == "reporting"


@pytest.mark.unit
def test_plan_for_release_readiness():
    nodes = plan_for({"kind": "release.readiness"}, available_agents=[])
    assert {n.agent for n in nodes} == {"reporting", "release_readiness"}


@pytest.mark.unit
def test_plan_for_self_heal_run():
    nodes = plan_for({"kind": "self_heal_run"}, available_agents=[])
    assert {n.agent for n in nodes} == {"execution", "self_healing"}


@pytest.mark.unit
def test_validate_dag_detects_cycle():
    n1 = PlanNode(node_id="n1", agent="x", depends_on=("n2",))
    n2 = PlanNode(node_id="n2", agent="x", depends_on=("n1",))
    with pytest.raises(ValueError, match="cycle"):
        _validate_dag([n1, n2])


@pytest.mark.unit
def test_validate_dag_detects_missing_dep():
    n1 = PlanNode(node_id="n1", agent="x", depends_on=("nope",))
    with pytest.raises(ValueError, match="unknown"):
        _validate_dag([n1])


@pytest.mark.unit
def test_validate_dag_ok():
    n1 = PlanNode(node_id="n1", agent="x")
    n2 = PlanNode(node_id="n2", agent="x", depends_on=("n1",))
    _validate_dag([n1, n2])


@pytest.mark.unit
def test_trim_to_cost_keeps_required_when_within_ceiling():
    required = PlanNode(node_id="r1", agent="planner", inputs={})
    optional = PlanNode(node_id="o1", agent="planner", inputs={"optional": True})
    # cost(2x planner) = 0.10, ceiling = 0.20 → keep both
    kept = _trim_to_cost([required, optional], ceiling=0.20)
    assert any(n.node_id == "r1" for n in kept)
    assert any(n.node_id == "o1" for n in kept)


@pytest.mark.unit
def test_trim_to_cost_drops_optional_first():
    required = PlanNode(node_id="r1", agent="planner", inputs={})
    optional = PlanNode(node_id="o1", agent="planner", inputs={"optional": True})
    # cost(2x planner) = 0.10, ceiling = 0.06 → drop optional (cheapest path)
    kept = _trim_to_cost([required, optional], ceiling=0.06)
    assert any(n.node_id == "r1" for n in kept)
    assert not any(n.node_id == "o1" for n in kept)


@pytest.mark.unit
def test_trim_to_cost_drops_required_when_required_alone_exceeds():
    required = PlanNode(node_id="r1", agent="planner", inputs={})
    optional = PlanNode(node_id="o1", agent="planner", inputs={"optional": True})
    # cost(2x planner) = 0.10, ceiling = 0.03 → must drop one of them
    kept = _trim_to_cost([required, optional], ceiling=0.03)
    assert len(kept) == 0 or len(kept) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_planner_plan_id_is_ulid():
    register_all()
    register_compute_handlers()
    agent = PlannerAgent()
    req = InvocationRequest(
        agent_name="planner",
        input={
            "goal": {"goal_id": "g1", "kind": "run_tests", "description": "d", "tenant_id": "t1"},
            "tenant_id": "t1",
        },
        tenant_id="t1",
    )
    out = await agent.invoke(req)
    from intelliqx_core.ids import is_valid_id

    assert is_valid_id(out["plan_id"])


@pytest.mark.unit
def test_planner_registered():
    register_all()
    reg = get_agent_registry()
    assert "planner" in reg.list()
