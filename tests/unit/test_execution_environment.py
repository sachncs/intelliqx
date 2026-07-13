"""Tests for  Environment Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest

from agents import register_all, register_compute_handlers
from agents.execution.environment import EnvironmentAgent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_environment_provisions_reference_app():
    register_all()
    register_compute_handlers()
    agent = EnvironmentAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="environment",
            input={
                "app_path": "tests.fixtures.reference_app.app",
                "port": 0,
                "health_path": "/health",
                "timeout_seconds": 10,
                "tenant_id": "t1",
            },
            tenant_id="t1",
        )
    )
    assert out["ready"]
    assert out["base_url"].startswith("http://127.0.0.1:")
    assert out["health"] == "/health"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_environment_health_endpoint_responds():
    register_all()
    register_compute_handlers()
    agent = EnvironmentAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="environment",
            input={"port": 0, "health_path": "/health", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    import httpx

    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{out['base_url']}/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_environment_fails_for_unreachable_app():
    """An environment whose server can't bind should raise RuntimeError."""
    register_all()
    register_compute_handlers()
    agent = EnvironmentAgent()
    # Patch the agent to use a bogus app path so it fails to bind
    from agents.execution import environment as env_module

    original = env_module._find_free_port

    def bogus_app():
        return 1  # reserved port, uvicorn will fail to bind

    env_module._find_free_port = bogus_app
    try:
        with pytest.raises(RuntimeError):
            await agent.invoke(
                InvocationRequest(
                    agent_name="environment",
                    input={
                        "port": 0,
                        "health_path": "/health",
                        "timeout_seconds": 1,
                        "tenant_id": "t1",
                    },
                    tenant_id="t1",
                )
            )
    finally:
        env_module._find_free_port = original
