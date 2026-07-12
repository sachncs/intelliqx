"""Tests for aqip-core."""

from datetime import datetime

import pytest
from intelliqx_core.errors import (
    AQIPError,
    CloudConfigError,
    ContractError,
    NotFoundError,
    ValidationError,
)
from intelliqx_core.events import BaseEvent, EventEnvelope, EventMetadata
from intelliqx_core.ids import is_valid_id, new_id, parse_id
from intelliqx_core.models import (
    AgentCapability,
    AgentRef,
    CloudProvider,
    Goal,
    HealthStatus,
    PlanNode,
    RunStatus,
    TenantContext,
)


@pytest.mark.unit
def test_new_id_is_valid_ulid():
    for _ in range(100):
        i = new_id()
        assert is_valid_id(i)
        assert parse_id(i) is not None


@pytest.mark.unit
def test_invalid_ulid():
    with pytest.raises(ValueError):
        parse_id("not-a-ulid")


@pytest.mark.unit
def test_goal_creation():
    g = Goal(goal_id=new_id(), tenant_id="t1", kind="analyze_prd", description="d")
    assert g.tenant_id == "t1"
    assert g.kind == "analyze_prd"
    assert isinstance(g.created_at, datetime)


@pytest.mark.unit
def test_goal_rejects_extra_fields():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Goal(goal_id="x", tenant_id="t1", kind="k", description="d", bogus=1)


@pytest.mark.unit
def test_plan_node_dependencies():
    p = PlanNode(node_id="n1", agent="planner", depends_on=("n0",))
    assert p.depends_on == ("n0",)


@pytest.mark.unit
def test_event_envelope_roundtrip():
    md = EventMetadata(tenant_id="t1", produced_by="test")
    e = BaseEvent(detail_type="PlanGenerated", metadata=md)
    env = EventEnvelope.from_event(e, md)
    assert env.detail_type == "BaseEvent"
    assert env.payload["detail_type"] == "PlanGenerated"


@pytest.mark.unit
def test_tenant_context_frozen():
    from pydantic import ValidationError

    t = TenantContext(tenant_id="t1")
    with pytest.raises(ValidationError):
        t.tenant_id = "t2"


@pytest.mark.unit
def test_cloud_provider_enum():
    assert CloudProvider.AWS.value == "aws"
    assert CloudProvider.GCP.value == "gcp"
    assert CloudProvider.MODAL.value == "modal"
    assert CloudProvider.LOCAL.value == "local"


@pytest.mark.unit
def test_run_status_enum():
    for s in RunStatus:
        assert s.value in {"PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "PAUSED"}


@pytest.mark.unit
def test_agent_capability_defaults():
    c = AgentCapability(name="x", description="y")
    assert c.cost_ceiling_usd is None
    assert c.latency_sla_ms is None


@pytest.mark.unit
def test_agent_ref():
    r = AgentRef(name="planner", tier=1)
    assert r.tier == 1


@pytest.mark.unit
def test_health_status_enum():
    assert HealthStatus.HEALTHY.value == "HEALTHY"


@pytest.mark.unit
def test_error_hierarchy():
    assert issubclass(CloudConfigError, AQIPError)
    assert issubclass(ContractError, AQIPError)
    assert issubclass(NotFoundError, AQIPError)
    assert issubclass(ValidationError, AQIPError)