"""Event bus interface and in-process implementation.

The :class:`EventBus` is the contract every adapter fulfils. Its
publish, subscribe, unsubscribe, and dead-letter operations share the
same interface across in-memory and any registered adapter.

Plus lifecycle hooks (``start`` / ``stop``); the in-memory
implementation treats them as no-ops.
"""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from collections.abc import Callable

from pydantic import BaseModel

from intelliqx_events.base import EventBus
from intelliqx_events.handler import EventHandler

__all__ = [
    "EVENT_BUS_REGISTRY",
    "InMemoryEventBus",
    "get_event_bus",
    "list_event_bus_backends",
    "register_event_bus_backend",
    "reset_event_bus",
]


class InMemoryEventBus(EventBus):
    """In-process event bus used for tests and local dev.

    Subscriptions run inside the same event loop as the publisher.
    Handlers may be sync or async; async handlers are awaited inline.
    Errors are routed to the subscription's DLQ (if any); otherwise
    they propagate.
    """

    __slots__ = ("dlqs", "next_sub_id", "started", "subscription_ids", "subscriptions")

    def __init__(self) -> None:
        # topic -> ordered list of handlers
        self.subscriptions: dict[str, list[EventHandler]] = defaultdict(list)
        self.subscription_ids: dict[str, tuple[str, EventHandler]] = {}
        self.next_sub_id = 0
        # dlq_name -> list of events that failed handling
        self.dlqs: dict[str, list[BaseModel]] = defaultdict(list)
        self.started = False

    async def publish(self, topic: str, event: BaseModel) -> str:
        """Fan out ``event`` to every subscriber of ``topic``.

        Returns:
            The event id. We prefer the metadata's ULID; for events
            without metadata we synthesise a local id from ``id()``.
        """
        event_id = getattr(event, "metadata", None)
        event_id = getattr(event_id, "event_id", None) or f"local-{id(event)}"
        # Snapshot the handler list to avoid surprises if a handler
        # subscribes/unsubscribes during dispatch.
        for handler in list(self.subscriptions.get(topic, [])):
            try:
                result = handler.handle(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                if handler.dlq:
                    await self.dlq(event, handler.dlq)
                else:
                    raise
        return str(event_id)

    def subscribe(
        self, topic: str, handler: Callable | EventHandler, *, dlq: str | None = None
    ) -> str:
        """Register a handler. See :meth:`EventBus.subscribe`."""
        self.next_sub_id += 1
        sub_id = f"sub-{self.next_sub_id}"
        if not isinstance(handler, EventHandler):
            # Wrap a bare callable with a default name (the function's
            # ``__name__``) and the supplied DLQ.
            handler = EventHandler(name=handler.__name__, callback=handler, dlq=dlq)
        else:
            # Override the handler's DLQ if the caller specified one.
            handler = handler.model_copy(update={"dlq": dlq or handler.dlq})
        self.subscriptions[topic].append(handler)
        self.subscription_ids[sub_id] = (topic, handler)
        return sub_id

    def unsubscribe(self, subscription_id: str | None = None) -> None:
        """Remove a subscription, or all subscriptions when no id is provided."""
        if subscription_id is None:
            self.subscriptions.clear()
            self.subscription_ids.clear()
            return
        subscription = self.subscription_ids.pop(subscription_id, None)
        if subscription is None:
            return
        topic, handler = subscription
        self.subscriptions[topic] = [
            registered for registered in self.subscriptions[topic] if registered is not handler
        ]
        if not self.subscriptions[topic]:
            self.subscriptions.pop(topic, None)

    async def dlq(self, event: BaseModel, topic: str | None = None) -> None:
        """Park an event in an in-memory dead-letter queue."""
        self.dlqs[topic or "dlq"].append(event)

    def get_dlq(self, dlq_name: str) -> list[BaseModel]:
        """Return the events currently parked in a DLQ.

        Tests use this to assert that a misbehaving handler caused the
        expected DLQ traffic. The list is a copy; mutating it does
        not affect the bus.
        """
        return list(self.dlqs.get(dlq_name, []))

    def reset(self) -> None:
        """Drop every subscription and DLQ entry.

        Useful in test setup helpers.
        """
        self.subscriptions.clear()
        self.subscription_ids.clear()
        self.dlqs.clear()
        self.next_sub_id = 0

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False


EVENT_BUS_REGISTRY: dict[str, type[EventBus]] = {"memory": InMemoryEventBus}


def register_event_bus_backend(name: str, factory: type[EventBus]) -> None:
    """Register or replace an event bus backend factory."""
    EVENT_BUS_REGISTRY[name] = factory


def list_event_bus_backends() -> tuple[str, ...]:
    """Return the registered event bus backend names in sorted order."""
    return tuple(sorted(EVENT_BUS_REGISTRY))


SINGLETON: EventBus | None = None


def get_event_bus(backend: str | None = None) -> EventBus:
    """Return the singleton event bus selected from the backend registry."""
    global SINGLETON
    if SINGLETON is None:
        backend_name = backend or os.environ.get("INTELLIQX_EVENT_BUS_BACKEND", "memory")
        factory = EVENT_BUS_REGISTRY.get(backend_name)
        if factory is None:
            available = ", ".join(list_event_bus_backends())
            raise RuntimeError(
                f"Event bus backend {backend_name!r} not registered. "
                f"Available backends: {available}."
            )
        SINGLETON = factory()
    return SINGLETON


def reset_event_bus() -> None:
    """Clear the singleton event bus (for tests)."""
    global SINGLETON
    if isinstance(SINGLETON, InMemoryEventBus):
        SINGLETON.reset()
    SINGLETON = None
