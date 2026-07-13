"""Cross-cloud parity tests: the same agent produces identical structured output
across all cloud profiles (using fallback implementations)."""

import pytest
from intelliqx_compute.runtime import InvocationRequest, get_compute_runtime
from intelliqx_events.bus import get_event_bus
from intelliqx_storage.store import reset_object_store
from intelliqx_vector.index import reset_vector_index

from agents import register_all, register_compute_handlers
from agents.coordination.planner import PlannerAgent
from agents.coordination.smoke import SmokeAgent


def _setup_test_world(profile: str):
    """Reset singletons for an isolated test world."""
    reset_object_store()
    reset_vector_index()
    get_event_bus()  # initialise singleton
    register_all()
    register_compute_handlers()


def _swap_cloud_profile(monkeypatch, profile: str):
    """Set INTELLIQX_CLOUD and force adapter re-resolution."""
    monkeypatch.setenv("INTELLIQX_CLOUD", profile)


@pytest.mark.cross_cloud
@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["local", "aws", "gcp", "modal"])
async def test_smoke_agent_identical_output_across_profiles(monkeypatch, profile):
    _swap_cloud_profile(monkeypatch, profile)
    _setup_test_world(profile)

    agent = SmokeAgent()
    req = InvocationRequest(agent_name="smoke", input={"marker": "cross_cloud"}, tenant_id="t1")
    out = await agent.invoke(req)
    assert out["echo"] == "cross_cloud"
    assert out["metadata"]["tenant"] == "t1"


@pytest.mark.cross_cloud
@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["local", "aws", "gcp", "modal"])
async def test_planner_identical_plan_across_profiles(monkeypatch, profile):
    _swap_cloud_profile(monkeypatch, profile)
    _setup_test_world(profile)

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
    # Same agent set regardless of cloud profile
    agent_names = sorted({n["agent"] for n in out["nodes"]})
    # run_tests template: environment, execution, failure_analysis (optional)
    assert "environment" in agent_names
    assert "execution" in agent_names


@pytest.mark.cross_cloud
@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["local", "aws", "gcp", "modal"])
async def test_compute_runtime_invokes_agent_across_profiles(monkeypatch, profile):
    _swap_cloud_profile(monkeypatch, profile)
    _setup_test_world(profile)
    runtime = get_compute_runtime()
    req = InvocationRequest(
        agent_name="smoke", input={"marker": f"profile-{profile}"}, tenant_id="t1"
    )
    resp = await runtime.invoke(req)
    # All profiles use InProcessComputeRuntime in tests (cloud adapters require creds)
    assert resp.status == "ok"
    assert resp.output["echo"] == f"profile-{profile}"
