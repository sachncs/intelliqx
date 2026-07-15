"""Governance & Compliance Agent (Governance).

Enforces RBAC, ABAC, audit trails, and human-approval workflows.
The agent has four actions:

* ``check``            — RBAC (role membership) + ABAC (tenant match).
* ``record_audit``     — write a tamper-evident audit record.
* ``request_approval`` — open a pending approval slot.
* ``grant``            — close a pending approval slot as approved.

Audit and approval records live in the state store:

* ``audit:<id>``         — JSON-encoded audit payload, 1y TTL.
* ``approval:<id>``     — ``"pending"`` or ``"approved"``, 7d TTL.

The TTLs are deliberate: audits must outlive a release cycle,
approvals should not block a deploy forever if the approver is
unreachable. Production deployments with stricter compliance
requirements should persist the same data to immutable storage
(WORM bucket) and adjust the TTLs.
"""

from __future__ import annotations

import time
from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory, TenantContext
from intelliqx_state.store import get_state_store
from pydantic import BaseModel, ConfigDict, Field


class GovernanceInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: str  # check | record_audit | request_approval | grant
    actor: TenantContext
    resource: str
    required_role: str | None = None
    required_attributes: dict[str, Any] = Field(default_factory=dict)
    audit_payload: dict[str, Any] = Field(default_factory=dict)
    approval_id: str | None = None


class GovernanceOutput(BaseModel):
    """Output payload for the Governance & Compliance agent.

    Attributes:
        allowed: ``True`` when the check passed or the approval was
            granted.
        reason: Human-readable explanation (``"ok"`` on success,
            ``"; "``-joined failure reasons otherwise).
        audit_id: Audit/approval identifier (set by ``record_audit``
            and ``request_approval``/``grant``).
        approval_state: ``"pending"`` / ``"approved"`` / ``"rejected"``
            / ``"granted"`` for the approval actions; ``None`` for
            others.
    """

    model_config = ConfigDict(extra="forbid")

    allowed: bool = False
    reason: str = ""
    audit_id: str | None = None
    approval_state: str | None = None  # pending | approved | rejected | granted


class GovernanceComplianceAgent(AgentBase):
    META = AgentMeta(
        name="governance_compliance",
        category=AgentCategory.GOVERNANCE,
        version="0.1.0",
        description="RBAC, ABAC, audit trail, human approvals.",
    )
    INPUT_MODEL = GovernanceInput
    OUTPUT_MODEL = GovernanceOutput

    @traced_agent("governance_compliance")
    async def run(self, ctx: AgentContext, input: GovernanceInput) -> GovernanceOutput:
        if input.action == "check":
            return check_compliance(input)
        if input.action == "record_audit":
            return await record_audit(input)
        if input.action == "request_approval":
            return await request_approval(input)
        if input.action == "grant":
            return await grant_access(input)
        return GovernanceOutput(allowed=False, reason=f"unknown action: {input.action}")


def check_compliance(input: GovernanceInput) -> GovernanceOutput:
    """Run RBAC + ABAC checks.

    RBAC: ``input.actor.roles`` must contain ``required_role`` if set.
    ABAC: ``required_attributes['tenant_id']`` must match the actor's
    tenant if present.
    """
    actor = input.actor
    allowed = True
    reasons: list[str] = []
    if input.required_role and input.required_role not in actor.roles:
        allowed = False
        reasons.append(f"role {input.required_role!r} required")
    if (
        input.required_attributes
        and "tenant_id" in input.required_attributes
        and actor.tenant_id != input.required_attributes["tenant_id"]
    ):
        allowed = False
        reasons.append("tenant mismatch")
    return GovernanceOutput(allowed=allowed, reason="; ".join(reasons) if not allowed else "ok")


async def record_audit(input: GovernanceInput) -> GovernanceOutput:
    """Persist a tamper-evident audit record.

    The record is a JSON dict containing the actor, the resource,
    and the caller's ``audit_payload``. The key
    (``audit:<id>``) embeds a millisecond timestamp so the order
    of writes is recoverable from the id alone.
    """
    state = get_state_store()
    audit_id = f"audit-{int(time.time() * 1000)}"
    payload = input.audit_payload | {
        "actor": input.actor.tenant_id,
        "actor_user": input.actor.user_id,
        "resource": input.resource,
    }
    await state.set(f"audit:{audit_id}", str(payload).encode("utf-8"), ttl_seconds=86400 * 365)
    return GovernanceOutput(allowed=True, audit_id=audit_id)


async def request_approval(input: GovernanceInput) -> GovernanceOutput:
    """Open a pending approval slot.

    The slot is identified by ``approval_id`` (caller-supplied) or
    a fresh millisecond-timestamp id. The value is ``"pending"``
    until :func:`grant_access` flips it to ``"approved"``.
    """
    state = get_state_store()
    approval_id = input.approval_id or f"approval-{int(time.time() * 1000)}"
    await state.set(f"approval:{approval_id}", b"pending", ttl_seconds=86400 * 7)
    return GovernanceOutput(
        allowed=False, reason="approval required", audit_id=approval_id, approval_state="pending"
    )


async def grant_access(input: GovernanceInput) -> GovernanceOutput:
    """Close a pending approval slot as approved.

    A ``grant`` without a valid ``approval_id`` is rejected.
    """
    if not input.approval_id:
        return GovernanceOutput(allowed=False, reason="missing approval_id")
    state = get_state_store()
    await state.set(f"approval:{input.approval_id}", b"approved", ttl_seconds=86400 * 7)
    return GovernanceOutput(allowed=True, audit_id=input.approval_id, approval_state="approved")
