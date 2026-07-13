"""Tests for  Execution Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest
from intelliqx_storage.store import get_object_store

from agents import register_all, register_compute_handlers
from agents.execution.environment import EnvironmentAgent
from agents.execution.execution import ExecutionAgent, TestSpec, TestStep


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execution_runs_passing_test():
    register_all()
    register_compute_handlers()
    env = EnvironmentAgent()
    env_out = await env.invoke(
        InvocationRequest(
            agent_name="environment",
            input={"port": 0, "health_path": "/health", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    base_url = env_out["base_url"]

    agent = ExecutionAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="execution",
            input={
                "base_url": base_url,
                "tenant_id": "t1",
                "tests": [
                    TestSpec(
                        name="health_check",
                        steps=[TestStep(action="get", path="/health", expected_status=200)],
                    ).model_dump()
                ],
            },
            tenant_id="t1",
        )
    )
    assert out["passed"] == 1
    assert out["failed"] == 0
    assert out["results"][0]["status"] == "passed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execution_reports_failure_on_bad_status():
    register_all()
    register_compute_handlers()
    env = EnvironmentAgent()
    env_out = await env.invoke(
        InvocationRequest(
            agent_name="environment",
            input={"port": 0, "health_path": "/health", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    base_url = env_out["base_url"]

    agent = ExecutionAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="execution",
            input={
                "base_url": base_url,
                "tenant_id": "t1",
                "tests": [
                    TestSpec(
                        name="wrong_status",
                        steps=[TestStep(action="get", path="/health", expected_status=404)],
                    ).model_dump()
                ],
            },
            tenant_id="t1",
        )
    )
    assert out["failed"] == 1
    assert out["results"][0]["status"] == "failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execution_post_step():
    register_all()
    register_compute_handlers()
    env = EnvironmentAgent()
    env_out = await env.invoke(
        InvocationRequest(
            agent_name="environment",
            input={"port": 0, "health_path": "/health", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    base_url = env_out["base_url"]

    agent = ExecutionAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="execution",
            input={
                "base_url": base_url,
                "tenant_id": "t1",
                "tests": [
                    TestSpec(
                        name="login_ok",
                        steps=[
                            TestStep(
                                action="post",
                                path="/login",
                                payload={"username": "admin", "password": "secret"},
                                expected_status=200,
                            )
                        ],
                    ).model_dump()
                ],
            },
            tenant_id="t1",
        )
    )
    assert out["results"][0]["status"] == "passed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execution_uploads_artifacts():
    register_all()
    register_compute_handlers()
    env = EnvironmentAgent()
    env_out = await env.invoke(
        InvocationRequest(
            agent_name="environment",
            input={"port": 0, "health_path": "/health", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    base_url = env_out["base_url"]

    agent = ExecutionAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="execution",
            input={
                "base_url": base_url,
                "tenant_id": "t1",
                "tests": [
                    TestSpec(
                        name="artifact_test",
                        steps=[TestStep(action="get", path="/", expected_status=200)],
                    ).model_dump()
                ],
            },
            tenant_id="t1",
        )
    )
    assert len(out["artifact_keys"]) >= 1
    store = get_object_store()
    key = out["artifact_keys"][0]
    data = await store.get(key)
    assert b"artifact_test" in data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execution_assert_json():
    register_all()
    register_compute_handlers()
    env = EnvironmentAgent()
    env_out = await env.invoke(
        InvocationRequest(
            agent_name="environment",
            input={"port": 0, "health_path": "/health", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    base_url = env_out["base_url"]

    agent = ExecutionAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="execution",
            input={
                "base_url": base_url,
                "tenant_id": "t1",
                "tests": [
                    TestSpec(
                        name="json_check",
                        steps=[
                            TestStep(
                                action="assert_json", path="/health", expected_json={"status": "ok"}
                            )
                        ],
                    ).model_dump()
                ],
            },
            tenant_id="t1",
        )
    )
    assert out["results"][0]["status"] == "passed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execution_multiple_tests_summary():
    register_all()
    register_compute_handlers()
    env = EnvironmentAgent()
    env_out = await env.invoke(
        InvocationRequest(
            agent_name="environment",
            input={"port": 0, "health_path": "/health", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    base_url = env_out["base_url"]

    agent = ExecutionAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="execution",
            input={
                "base_url": base_url,
                "tenant_id": "t1",
                "tests": [
                    TestSpec(
                        name="t1",
                        steps=[TestStep(action="get", path="/health", expected_status=200)],
                    ).model_dump(),
                    TestSpec(
                        name="t2",
                        steps=[TestStep(action="get", path="/health", expected_status=404)],
                    ).model_dump(),
                ],
            },
            tenant_id="t1",
        )
    )
    assert out["passed"] == 1
    assert out["failed"] == 1
