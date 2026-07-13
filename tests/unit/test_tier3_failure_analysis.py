"""Tests for Tier 3 Failure Analysis Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest

from agents import register_all, register_compute_handlers
from agents.execution.failure_analysis import FailureAnalysisAgent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failure_classified_as_infra():
    register_all()
    register_compute_handlers()
    agent = FailureAnalysisAgent()
    for err in (
        "ConnectionError: ECONNREFUSED",
        "TimeoutError: request exceeded 30s",
        "SSLError: CERTIFICATE_VERIFY_FAILED",
        "503 Service Unavailable",
    ):
        out = await agent.invoke(
            InvocationRequest(
                agent_name="failure_analysis",
                input={"error": err, "test_name": "t"},
                tenant_id="t1",
            )
        )
        assert out["classification"] == "infra", f"expected infra for {err!r}"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failure_classified_as_product():
    register_all()
    register_compute_handlers()
    agent = FailureAnalysisAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="failure_analysis",
            input={"error": "AssertionError: expected 200 but got 500"},
            tenant_id="t1",
        )
    )
    assert out["classification"] == "product"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failure_classified_as_flake_when_history_passes():
    register_all()
    register_compute_handlers()
    agent = FailureAnalysisAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="failure_analysis",
            input={
                "error": "500 error",
                "retry_count": 1,
                "history": [{"status": "passed", "attempt": 1}, {"status": "failed", "attempt": 2}],
            },
            tenant_id="t1",
        )
    )
    assert out["classification"] == "flake"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failure_404_classified_as_product():
    register_all()
    register_compute_handlers()
    agent = FailureAnalysisAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="failure_analysis",
            input={"error": "got 404", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert out["classification"] == "product"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failure_unknown_error():
    register_all()
    register_compute_handlers()
    agent = FailureAnalysisAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="failure_analysis", input={"error": "wat", "tenant_id": "t1"}, tenant_id="t1"
        )
    )
    assert out["classification"] == "unknown"
    assert out["confidence"] <= 0.6


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failure_returns_root_cause_and_action():
    register_all()
    register_compute_handlers()
    agent = FailureAnalysisAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="failure_analysis",
            input={"error": "ECONNREFUSED", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert out["root_cause"]
    assert out["suggested_action"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failure_401_auth_routing_defect():
    register_all()
    register_compute_handlers()
    agent = FailureAnalysisAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="failure_analysis",
            input={"error": "401 unauthorized", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert out["classification"] == "product"
    assert "Auth" in out["root_cause"] or "auth" in out["root_cause"].lower()
