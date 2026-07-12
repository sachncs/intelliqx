"""Tests for Tier 3 Performance Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest

from agents import register_all, register_compute_handlers
from agents.tier3.environment import EnvironmentAgent
from agents.tier3.performance import PerformanceAgent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_performance_runs_against_endpoint():
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

    perf = PerformanceAgent()
    out = await perf.invoke(
        InvocationRequest(
            agent_name="performance",
            input={
                "tenant_id": "t1",
                "target_url": f"{base_url}/health",
                "profile": "load",
                "duration_seconds": 2,
                "concurrency": 3,
                "slo_p95_ms": 5000,
                "slo_error_rate": 0.5,
            },
            tenant_id="t1",
        )
    )
    assert out["profile"] == "load"
    assert out["result"]["requests"] > 0
    assert out["result"]["slo_pass"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_performance_breach_on_impossible_slo():
    register_all()
    register_compute_handlers()
    perf = PerformanceAgent()
    out = await perf.invoke(
        InvocationRequest(
            agent_name="performance",
            input={
                "tenant_id": "t1",
                "target_url": "http://127.0.0.1:1/health",
                "duration_seconds": 1,
                "concurrency": 1,
                "slo_p95_ms": 0.001,  # impossible
                "slo_error_rate": 0.0,
            },
            tenant_id="t1",
        )
    )
    assert not out["result"]["slo_pass"]
    assert len(out["slo_breaches"]) >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_performance_percentiles_calculated():
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

    perf = PerformanceAgent()
    out = await perf.invoke(
        InvocationRequest(
            agent_name="performance",
            input={
                "tenant_id": "t1",
                "target_url": f"{base_url}/health",
                "duration_seconds": 1,
                "concurrency": 2,
            },
            tenant_id="t1",
        )
    )
    r = out["result"]
    assert r["p50_ms"] <= r["p95_ms"] <= r["p99_ms"] or r["p99_ms"] == 0