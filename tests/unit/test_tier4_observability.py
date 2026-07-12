"""Tests for Tier 4 Observability Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest
from intelliqx_observability.metrics import get_metrics

from agents import register_all, register_compute_handlers
from agents.tier4.observability import ObservabilityAgent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_observability_returns_snapshot():
    register_all()
    register_compute_handlers()
    agent = ObservabilityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="observability",
            input={"window_seconds": 3600, "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert "counters" in out["snapshot"]
    assert "gauges" in out["snapshot"]
    assert "histograms" in out["snapshot"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_observability_returns_sla_records():
    register_all()
    register_compute_handlers()
    agent = ObservabilityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="observability",
            input={"tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    names = {s["name"] for s in out["slas"]}
    assert "agent_latency_ms" in names
    assert "agent_success_rate" in names


@pytest.mark.unit
@pytest.mark.asyncio
async def test_observability_sla_compliance_reflects_metrics():
    register_all()
    register_compute_handlers()
    metrics = get_metrics()
    counter = metrics.counter("agent.ok")
    counter.inc(10)
    counter = metrics.counter("agent.err")
    counter.inc(1)
    agent = ObservabilityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="observability",
            input={"tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    success_rate_sla = next(s for s in out["slas"] if s["name"] == "agent_success_rate")
    # 10/11 ≈ 0.909; SLA target 0.95 → not compliant
    assert success_rate_sla["compliant"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_observability_window_param_accepted():
    register_all()
    register_compute_handlers()
    agent = ObservabilityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="observability",
            input={"window_seconds": 7200, "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert out["snapshot"]