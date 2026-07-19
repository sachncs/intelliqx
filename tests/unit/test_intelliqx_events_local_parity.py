"""Local-backend parity tests for intelliqx-events.

Asserts that the in-memory event bus covers the publish/subscribe
contract on the local-only platform.
"""

import pytest
from intelliqx_core.events import BaseEvent, EventMetadata
from intelliqx_events.bus import InMemoryEventBus


@pytest.mark.unit
@pytest.mark.asyncio
async def test_publish_subscribe_contract():
    bus = InMemoryEventBus()
    received: list[str] = []

    def handler(e: BaseEvent) -> None:
        received.append(e.detail_type)

    bus.subscribe("topic.a", handler)
    md = EventMetadata(tenant_id="t1", produced_by="test")
    await bus.publish("topic.a", BaseEvent(detail_type="LocalEvent", metadata=md))
    assert received == ["LocalEvent"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dlq_contract():
    bus = InMemoryEventBus()

    def bad(_e):
        raise RuntimeError("boom")

    bus.subscribe("topic.a", bad, dlq="topic.a.dlq")
    md = EventMetadata(tenant_id="t1", produced_by="test")
    await bus.publish("topic.a", BaseEvent(detail_type="X", metadata=md))
    assert len(bus.get_dlq("topic.a.dlq")) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multiple_subscribers_contract():
    bus = InMemoryEventBus()
    r1, r2 = [], []

    bus.subscribe("topic", lambda e: r1.append(e.detail_type))
    bus.subscribe("topic", lambda e: r2.append(e.detail_type))
    md = EventMetadata(tenant_id="t1", produced_by="test")
    await bus.publish("topic", BaseEvent(detail_type="M", metadata=md))
    assert len(r1) == 1
    assert len(r2) == 1
