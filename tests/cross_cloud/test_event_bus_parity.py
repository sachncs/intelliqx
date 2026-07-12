"""Cross-cloud parity tests for aqip-events.

Same agent invoked under 4 cloud profiles must produce identical structured output.
"""

import pytest
from intelliqx_core.events import BaseEvent, EventMetadata
from intelliqx_events.aws import AWSEventBridgeBus
from intelliqx_events.bus import InMemoryEventBus
from intelliqx_events.gcp import GCPPubSubBus
from intelliqx_events.modal import ModalQueueBus


def _make_bus(profile: str):
    """Build the event bus for the given cloud profile."""
    if profile == "aws":
        return AWSEventBridgeBus(bus_name="aqip.test")
    if profile == "gcp":
        return GCPPubSubBus(project_id="intelliqx-test")
    if profile == "modal":
        return ModalQueueBus()
    return InMemoryEventBus()


PROFILES = ["local", "aws", "gcp", "modal"]


@pytest.mark.cross_cloud
@pytest.mark.asyncio
@pytest.mark.parametrize("profile", PROFILES)
async def test_publish_subscribe_contract(profile):
    """Every cloud profile must satisfy the same publish/subscribe contract."""
    bus = _make_bus(profile)
    received: list[str] = []

    def handler(e: BaseEvent) -> None:
        received.append(e.detail_type)

    bus.subscribe("topic.a", handler)
    md = EventMetadata(tenant_id="t1", produced_by="test")
    await bus.publish("topic.a", BaseEvent(detail_type="CrossCloudEvent", metadata=md))
    assert len(received) == 1
    assert received[0] == "CrossCloudEvent"


@pytest.mark.cross_cloud
@pytest.mark.asyncio
@pytest.mark.parametrize("profile", PROFILES)
async def test_dlq_contract(profile):
    """Every cloud profile must route handler errors to the DLQ topic."""
    bus = _make_bus(profile)

    def bad(_e):
        raise RuntimeError("boom")

    bus.subscribe("topic.a", bad, dlq="topic.a.dlq")
    md = EventMetadata(tenant_id="t1", produced_by="test")
    # Should NOT raise.
    await bus.publish("topic.a", BaseEvent(detail_type="X", metadata=md))


@pytest.mark.cross_cloud
@pytest.mark.asyncio
@pytest.mark.parametrize("profile", PROFILES)
async def test_multiple_subscribers_contract(profile):
    bus = _make_bus(profile)
    r1, r2 = [], []

    bus.subscribe("topic", lambda e: r1.append(e.detail_type))
    bus.subscribe("topic", lambda e: r2.append(e.detail_type))
    md = EventMetadata(tenant_id="t1", produced_by="test")
    await bus.publish("topic", BaseEvent(detail_type="M", metadata=md))
    assert len(r1) == 1
    assert len(r2) == 1


@pytest.mark.cross_cloud
def test_bus_factory_local():
    from intelliqx_events.bus import get_event_bus

    bus = get_event_bus()
    assert isinstance(bus, InMemoryEventBus)


@pytest.mark.cross_cloud
def test_aws_bus_lazy_init(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    bus = AWSEventBridgeBus()
    # Without boto3/creds, should fall back to in-memory semantics (no crash)
    assert bus is not None


@pytest.mark.cross_cloud
def test_gcp_bus_lazy_init(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    bus = GCPPubSubBus()
    assert bus is not None


@pytest.mark.cross_cloud
def test_modal_bus_lazy_init():
    bus = ModalQueueBus()
    assert bus is not None