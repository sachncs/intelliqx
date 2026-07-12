"""Tests for Tier 3 Cost Optimization Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest
from intelliqx_observability.metrics import get_metrics

from agents import register_all, register_compute_handlers
from agents.tier3.cost_optimization import CostOptimizationAgent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cost_opt_returns_recommendations():
    register_all()
    register_compute_handlers()
    metrics = get_metrics()
    metrics.counter("agent.invocation").inc(100)
    agent = CostOptimizationAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="cost_optimization",
            input={"tenant_id": "t1", "window_days": 30},
            tenant_id="t1",
        )
    )
    assert out["recommendations"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cost_opt_detects_long_tail_histogram():
    register_all()
    register_compute_handlers()
    metrics = get_metrics()
    h = metrics.histogram("agent.duration")
    # Add samples with high p99/p50 ratio
    for v in [10] * 90 + [200] * 10:
        h.observe(float(v))
    agent = CostOptimizationAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="cost_optimization",
            input={"tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert any("spot" in r["action"] or "long_tail" in r["action"] for r in out["recommendations"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cost_opt_estimates_total_savings():
    register_all()
    register_compute_handlers()
    metrics = get_metrics()
    metrics.counter("agent.invocation").inc(1000)
    agent = CostOptimizationAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="cost_optimization",
            input={"tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert out["estimated_total_savings_usd"] >= 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cost_opt_empty_metrics_returns_savings():
    register_all()
    register_compute_handlers()
    agent = CostOptimizationAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="cost_optimization",
            input={"tenant_id": "t1", "window_days": 7},
            tenant_id="t1",
        )
    )
    assert "recommendations" in out
    assert "estimated_total_savings_usd" in out