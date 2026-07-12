"""Tests for aqip-events."""

import pytest
from aqip_core.events import BaseEvent, EventMetadata
from aqip_events.bus import InMemoryEventBus, get_event_bus
from aqip_events.handler import EventHandler
from aqip_events.schemas import EventContract, EventRegistry


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_memory_publish_subscribe():
    bus = InMemoryEventBus()
    received: list[BaseEvent] = []

    def handler(e: BaseEvent) -> None:
        received.append(e)

    bus.subscribe("topic.a", handler)
    md = EventMetadata(tenant_id="t1", produced_by="test")
    event = BaseEvent(detail_type="Test", metadata=md)
    await bus.publish("topic.a", event)
    assert len(received) == 1
    assert received[0] is event


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_memory_dlq_on_error():
    bus = InMemoryEventBus()

    def handler(e: BaseEvent) -> None:
        raise RuntimeError("boom")

    bus.subscribe("topic.a", handler, dlq="topic.a.dlq")
    md = EventMetadata(tenant_id="t1", produced_by="test")
    event = BaseEvent(detail_type="Test", metadata=md)
    # Should not raise — DLQ absorbs it.
    await bus.publish("topic.a", event)
    dlq = bus.get_dlq("topic.a.dlq")
    assert len(dlq) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_memory_reraises_without_dlq():
    bus = InMemoryEventBus()

    def handler(e: BaseEvent) -> None:
        raise RuntimeError("boom")

    bus.subscribe("topic.a", handler)
    md = EventMetadata(tenant_id="t1", produced_by="test")
    event = BaseEvent(detail_type="Test", metadata=md)
    with pytest.raises(RuntimeError):
        await bus.publish("topic.a", event)


@pytest.mark.unit
def test_event_handler_dataclass():
    def cb(e):
        return e

    h = EventHandler(name="h", callback=cb, dlq="d")
    assert h.name == "h"
    assert h.dlq == "d"


@pytest.mark.unit
def test_event_registry_register_and_get():
    EventRegistry._contracts.clear()
    c = EventContract(topic="t.x", description="d", schema_={"type": "object"})
    EventRegistry.register(c)
    assert EventRegistry.get("t.x").description == "d"
    assert "t.x" in EventRegistry.all()


@pytest.mark.unit
def test_event_registry_get_missing():
    EventRegistry._contracts.clear()
    with pytest.raises(KeyError):
        EventRegistry.get("missing")


@pytest.mark.unit
def test_event_registry_validate_known_topic():
    """Validation runs without error for a registered topic with any payload."""
    EventRegistry._contracts.clear()
    EventRegistry.register(
        EventContract(topic="t.x", description="d", schema_={"type": "object"})
    )
    # Should not raise even though schema is valid for the payload.
    EventRegistry.validate("t.x", {"foo": "bar"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_singleton_bus():
    bus = get_event_bus()
    assert isinstance(bus, InMemoryEventBus)
    received: list[BaseEvent] = []

    def handler(e: BaseEvent) -> None:
        received.append(e)

    bus.subscribe("topic.s", handler)
    md = EventMetadata(tenant_id="t1", produced_by="test")
    await bus.publish("topic.s", BaseEvent(detail_type="T", metadata=md))
    assert len(received) == 1