"""Tests for Tier 4 Reporting Agent."""

import pytest
from aqip_compute.runtime import InvocationRequest

from agents import register_all, register_compute_handlers
from agents.tier4.reporting import ReportingAgent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reporting_produces_markdown():
    register_all()
    register_compute_handlers()
    agent = ReportingAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="reporting",
            input={
                "run_id": "r1",
                "tenant_id": "t1",
                "summary": {"total": 10, "ok": 8, "failed": 2},
            },
            tenant_id="t1",
        )
    )
    assert "# AQIP Run Report" in out["markdown"]
    assert "r1" in out["markdown"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reporting_produces_json():
    register_all()
    register_compute_handlers()
    agent = ReportingAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="reporting",
            input={
                "run_id": "r1",
                "tenant_id": "t1",
                "summary": {"total": 5, "ok": 5, "failed": 0},
            },
            tenant_id="t1",
        )
    )
    js = out["json_payload"]
    assert js["run_id"] == "r1"
    assert js["tenant_id"] == "t1"
    assert "generated_at" in js
    assert js["summary"]["total"] == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reporting_executive_summary_section():
    register_all()
    register_compute_handlers()
    agent = ReportingAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="reporting",
            input={
                "run_id": "r1",
                "tenant_id": "t1",
                "summary": {"total": 12, "ok": 10, "failed": 2},
            },
            tenant_id="t1",
        )
    )
    assert "Executive Summary" in out["markdown"]
    assert "12" in out["markdown"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reporting_without_metrics():
    register_all()
    register_compute_handlers()
    agent = ReportingAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="reporting",
            input={
                "run_id": "r1",
                "tenant_id": "t1",
                "summary": {},
                "include_metrics": False,
            },
            tenant_id="t1",
        )
    )
    assert "Metrics Snapshot" not in out["markdown"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reporting_with_metrics():
    register_all()
    register_compute_handlers()
    agent = ReportingAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="reporting",
            input={
                "run_id": "r1",
                "tenant_id": "t1",
                "summary": {"total": 1, "ok": 1, "failed": 0},
                "include_metrics": True,
            },
            tenant_id="t1",
        )
    )
    assert "Metrics Snapshot" in out["markdown"]