"""Phase 5 E2E: v1 GA release scenario.

Goal → Planner → Orchestrator → all agents → Release decision.
"""

import pytest
from intelliqx_compute.runtime import InvocationRequest
from intelliqx_core.models import RunStatus, TenantContext

from agents import register_all, register_compute_handlers
from agents.coordination.orchestrator import OrchestratorAgent
from agents.governance.governance_compliance import GovernanceComplianceAgent
from agents.governance.release_readiness import ReleaseReadinessAgent
from agents.governance.reporting import ReportingAgent


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_v1_release_scenario_go():
    """Healthy release → Go."""
    register_all()
    register_compute_handlers()

    orch = OrchestratorAgent()
    out = await orch.invoke(
        InvocationRequest(
            agent_name="orchestrator",
            input={
                "plan_id": "p-v1",
                "goal_id": "release-v1",
                "tenant_id": "t1",
                "run_id": "r-v1-go",
                "nodes": [
                    {
                        "node_id": "n1",
                        "agent": "reporting",
                        "inputs": {
                            "run_id": "r-v1-go",
                            "tenant_id": "t1",
                            "summary": {"total": 10, "ok": 10, "failed": 0},
                        },
                        "depends_on": [],
                    },
                    {
                        "node_id": "n2",
                        "agent": "release_readiness",
                        "inputs": {
                            "tenant_id": "t1",
                            "risk_score": 0.1,
                            "coverage_pct": 92.0,
                            "performance_slo_pass": True,
                            "security_findings_critical": 0,
                            "security_findings_high": 0,
                            "open_defects": 0,
                        },
                        "depends_on": ["n1"],
                    },
                ],
            },
            tenant_id="t1",
        )
    )
    assert out["status"] == RunStatus.SUCCEEDED.value
    rr = next(r for r in out["node_results"] if r["agent"] == "release_readiness")
    assert rr["output"]["recommendation"] == "go"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_v1_release_scenario_no_go():
    """Critical security findings → No-Go."""
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
                "security_findings_critical": 5,
            },
            tenant_id="t1",
        )
    )
    assert out["outcome"] == "failed"
    assert out["recommendation"] == "no_go"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_v1_governance_approval_workflow():
    """Release requires human approval via governance agent."""
    register_all()
    register_compute_handlers()
    gov = GovernanceComplianceAgent()

    # Admin requests approval
    req_out = await gov.invoke(
        InvocationRequest(
            agent_name="governance_compliance",
            input={
                "action": "request_approval",
                "actor": TenantContext(
                    tenant_id="t1", user_id="admin1", roles=("admin",)
                ).model_dump(),
                "resource": "production-deploy",
            },
            tenant_id="t1",
        )
    )
    assert req_out["approval_state"] == "pending"

    # Operator grants
    grant_out = await gov.invoke(
        InvocationRequest(
            agent_name="governance_compliance",
            input={
                "action": "grant",
                "actor": TenantContext(
                    tenant_id="t1", user_id="operator1", roles=("operator",)
                ).model_dump(),
                "resource": "production-deploy",
                "approval_id": req_out["audit_id"],
            },
            tenant_id="t1",
        )
    )
    assert grant_out["approval_state"] == "approved"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_v1_release_report_generated():
    """Reporting agent produces Markdown + JSON for a release."""
    register_all()
    register_compute_handlers()
    rep = ReportingAgent()
    out = await rep.invoke(
        InvocationRequest(
            agent_name="reporting",
            input={
                "run_id": "r-v1-final",
                "tenant_id": "t1",
                "summary": {"total": 50, "ok": 48, "failed": 2},
                "include_metrics": True,
            },
            tenant_id="t1",
        )
    )
    md = out["markdown"]
    js = out["json_payload"]
    assert "IntelliqX Run Report" in md
    assert "r-v1-final" in md
    assert js["summary"]["total"] == 50


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_v1_release_full_pipeline():
    """Full Goal → Orchestrator → Reporting → ReleaseReadiness."""
    register_all()
    register_compute_handlers()

    orch = OrchestratorAgent()
    out = await orch.invoke(
        InvocationRequest(
            agent_name="orchestrator",
            input={
                "plan_id": "p-v1-full",
                "goal_id": "release-v1-full",
                "tenant_id": "t1",
                "run_id": "r-v1-full",
                "nodes": [
                    {
                        "node_id": "n1",
                        "agent": "reporting",
                        "inputs": {
                            "run_id": "r-v1-full",
                            "tenant_id": "t1",
                            "summary": {"total": 100, "ok": 100, "failed": 0},
                            "include_metrics": False,
                        },
                        "depends_on": [],
                    },
                    {
                        "node_id": "n2",
                        "agent": "release_readiness",
                        "inputs": {
                            "tenant_id": "t1",
                            "risk_score": 0.1,
                            "coverage_pct": 90,
                            "performance_slo_pass": True,
                            "security_findings_critical": 0,
                            "security_findings_high": 0,
                            "open_defects": 0,
                        },
                        "depends_on": ["n1"],
                    },
                    {
                        "node_id": "n3",
                        "agent": "observability",
                        "inputs": {"window_seconds": 3600},
                        "depends_on": ["n1", "n2"],
                    },
                ],
            },
            tenant_id="t1",
        )
    )
    assert out["status"] == RunStatus.SUCCEEDED.value
    agents = [r["agent"] for r in out["node_results"]]
    assert "reporting" in agents
    assert "release_readiness" in agents
    assert "observability" in agents
