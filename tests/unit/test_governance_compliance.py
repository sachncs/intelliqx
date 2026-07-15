"""Tests for  Governance & Compliance Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest
from intelliqx_core.models import TenantContext
from intelliqx_state.store import get_state_store

from agents import register_all, register_compute_handlers
from agents.governance.governance_compliance import GovernanceComplianceAgent


def make_admin(tid: str = "t1") -> TenantContext:
    return TenantContext(tenant_id=tid, user_id="u1", roles=("admin",))


def make_no_role(tid: str = "t1") -> TenantContext:
    return TenantContext(tenant_id=tid, user_id="u1", roles=())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_rbac_allows_when_role_present():
    register_all()
    register_compute_handlers()
    agent = GovernanceComplianceAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="governance_compliance",
            input={
                "action": "check",
                "actor": make_admin().model_dump(),
                "resource": "prod",
                "required_role": "admin",
            },
            tenant_id="t1",
        )
    )
    assert out["allowed"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_rbac_denies_when_role_missing():
    register_all()
    register_compute_handlers()
    agent = GovernanceComplianceAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="governance_compliance",
            input={
                "action": "check",
                "actor": make_no_role().model_dump(),
                "resource": "prod",
                "required_role": "admin",
            },
            tenant_id="t1",
        )
    )
    assert not out["allowed"]
    assert "admin" in out["reason"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_abac_tenant_mismatch_denied():
    register_all()
    register_compute_handlers()
    agent = GovernanceComplianceAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="governance_compliance",
            input={
                "action": "check",
                "actor": make_admin("tA").model_dump(),
                "resource": "x",
                "required_attributes": {"tenant_id": "tB"},
            },
            tenant_id="tA",
        )
    )
    assert not out["allowed"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_record_audit_persists():
    register_all()
    register_compute_handlers()
    agent = GovernanceComplianceAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="governance_compliance",
            input={
                "action": "record_audit",
                "actor": make_admin().model_dump(),
                "resource": "release/1.2.3",
                "audit_payload": {"action": "deploy"},
            },
            tenant_id="t1",
        )
    )
    assert out["audit_id"]
    state = get_state_store()
    data = await state.get(f"audit:{out['audit_id']}")
    assert data is not None
    assert b"release/1.2.3" in data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_request_approval_returns_pending():
    register_all()
    register_compute_handlers()
    agent = GovernanceComplianceAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="governance_compliance",
            input={
                "action": "request_approval",
                "actor": make_admin().model_dump(),
                "resource": "prod-deploy",
            },
            tenant_id="t1",
        )
    )
    assert not out["allowed"]
    assert out["approval_state"] == "pending"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_grant_approval_marks_approved():
    register_all()
    register_compute_handlers()
    agent = GovernanceComplianceAgent()
    req_out = await agent.invoke(
        InvocationRequest(
            agent_name="governance_compliance",
            input={
                "action": "request_approval",
                "actor": make_admin().model_dump(),
                "resource": "prod-deploy",
            },
            tenant_id="t1",
        )
    )
    approval_id = req_out["audit_id"]
    grant_out = await agent.invoke(
        InvocationRequest(
            agent_name="governance_compliance",
            input={
                "action": "grant",
                "actor": make_admin().model_dump(),
                "resource": "prod-deploy",
                "approval_id": approval_id,
            },
            tenant_id="t1",
        )
    )
    assert grant_out["allowed"]
    assert grant_out["approval_state"] == "approved"
    state = get_state_store()
    assert await state.get(f"approval:{approval_id}") == b"approved"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_grant_requires_approval_id():
    register_all()
    register_compute_handlers()
    agent = GovernanceComplianceAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="governance_compliance",
            input={"action": "grant", "actor": make_admin().model_dump(), "resource": "prod-deploy"},
            tenant_id="t1",
        )
    )
    assert not out["allowed"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unknown_action_denied():
    register_all()
    register_compute_handlers()
    agent = GovernanceComplianceAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="governance_compliance",
            input={"action": "frobnicate", "actor": make_admin().model_dump(), "resource": "x"},
            tenant_id="t1",
        )
    )
    assert not out["allowed"]
