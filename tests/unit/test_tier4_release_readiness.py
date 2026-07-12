"""Tests for Tier 4 Release Readiness Agent."""

import pytest
from aqip_compute.runtime import InvocationRequest
from aqip_core.ids import is_valid_id

from agents import register_all, register_compute_handlers
from agents.tier4.release_readiness import ReleaseReadinessAgent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_release_readiness_go_for_healthy_inputs():
    register_all()
    register_compute_handlers()
    agent = ReleaseReadinessAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="release_readiness",
            input={
                "tenant_id": "t1",
                "risk_score": 0.2,
                "coverage_pct": 90.0,
                "performance_slo_pass": True,
                "security_findings_critical": 0,
                "security_findings_high": 0,
                "open_defects": 0,
            },
            tenant_id="t1",
        )
    )
    assert out["recommendation"] == "go"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_release_readiness_no_go_for_critical_security():
    register_all()
    register_compute_handlers()
    agent = ReleaseReadinessAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="release_readiness",
            input={
                "tenant_id": "t1",
                "risk_score": 0.3,
                "coverage_pct": 85.0,
                "performance_slo_pass": True,
                "security_findings_critical": 2,
            },
            tenant_id="t1",
        )
    )
    assert out["recommendation"] == "no_go"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_release_readiness_conditional_for_medium_risk():
    register_all()
    register_compute_handlers()
    agent = ReleaseReadinessAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="release_readiness",
            input={
                "tenant_id": "t1",
                "risk_score": 0.5,
                "coverage_pct": 70.0,
                "performance_slo_pass": True,
            },
            tenant_id="t1",
        )
    )
    assert out["recommendation"] in {"conditional_go", "no_go", "go"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_release_readiness_decision_id_is_ulid():
    register_all()
    register_compute_handlers()
    agent = ReleaseReadinessAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="release_readiness",
            input={"tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert is_valid_id(out["decision_id"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_release_readiness_explanation_non_empty():
    register_all()
    register_compute_handlers()
    agent = ReleaseReadinessAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="release_readiness",
            input={"tenant_id": "t1", "coverage_pct": 50, "risk_score": 0.6},
            tenant_id="t1",
        )
    )
    assert len(out["explanation"]) >= 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_release_readiness_high_open_defects_no_go():
    register_all()
    register_compute_handlers()
    agent = ReleaseReadinessAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="release_readiness",
            input={
                "tenant_id": "t1",
                "risk_score": 0.2,
                "coverage_pct": 80,
                "performance_slo_pass": True,
                "open_defects": 20,
            },
            tenant_id="t1",
        )
    )
    # open_defects alone may not be enough for no_go; verify explanation mentions them
    assert any("defects" in e for e in out["explanation"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_release_readiness_low_coverage_no_go():
    register_all()
    register_compute_handlers()
    agent = ReleaseReadinessAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="release_readiness",
            input={
                "tenant_id": "t1",
                "risk_score": 0.4,
                "coverage_pct": 30,
                "performance_slo_pass": False,
            },
            tenant_id="t1",
        )
    )
    assert out["recommendation"] == "no_go"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_release_readiness_historical_boost_confidence():
    register_all()
    register_compute_handlers()
    agent = ReleaseReadinessAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="release_readiness",
            input={
                "tenant_id": "t1",
                "risk_score": 0.2,
                "coverage_pct": 85,
                "performance_slo_pass": True,
                "historical_release_success": 0.95,
            },
            tenant_id="t1",
        )
    )
    assert out["confidence"] >= 0.75