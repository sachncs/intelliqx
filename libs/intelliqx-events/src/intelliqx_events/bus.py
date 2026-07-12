"""Event bus interface and in-process implementation.

The :class:`EventBus` is the contract every adapter fulfils. Two
methods:

* ``publish(topic, event)`` — fan-out delivery to every subscriber of
  ``topic``. Returns the event id (so callers can correlate).
* ``subscribe(topic, handler, *, dlq=None)`` — register a handler.
  ``dlq`` is the optional dead-letter topic; failed invocations are
  routed there instead of being raised (in-process) or sent to the
  cloud's native DLQ (cloud adapters).

Plus lifecycle hooks (``start`` / ``stop``) that cloud adapters use to
flush background workers; the in-memory implementation treats them
as no-ops.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable

from pydantic import BaseModel

from intelliqx_events.handler import EventHandler


class EventBus:
    """Abstract event bus.

    Subclasses must implement ``publish`` and ``subscribe``. The
    ``start`` / ``stop`` lifecycle hooks exist so cloud adapters
    can manage background workers; the in-memory bus treats them as
    no-ops.
    """

    async def publish(self, topic: str, event: BaseModel) -> str:
        """Publish an event to a topic.

        Args:
            topic: The topic name (e.g. ``"run.started"``).
            event: The event payload. Must expose a ``metadata`` field
                with at least ``event_id`` (see :mod:`intelliqx_core.events`).

        Returns:
            The event id, for correlation by the caller.
        """
        raise NotImplementedError

    def subscribe(
        self,
        topic: str,
        handler: Callable | EventHandler,
        *,
        dlq: str | None = None,
    ) -> str:
        """Register a handler for a topic.

        Args:
            topic: The topic to subscribe to.
            handler: Either a plain callable ``(event) -> None`` or a
                pre-built :class:`EventHandler`. Plain callables are
                wrapped with the provided ``dlq``; ``EventHandler``
                instances inherit their existing ``dlq`` unless
                overridden here.
            dlq: Optional dead-letter topic. On handler failure the
                event is published to ``{topic}.dlq`` instead of
                being raised (in-process) or sent to the cloud's
                native DLQ.

        Returns:
            A subscription id (string) that the caller can use to
            later unsubscribe (adapters that support it).
        """
        raise NotImplementedError

    async def start(self) -> None:
        """Start background tasks (cloud adapters only)."""

    async def stop(self) -> None:
        """Stop background tasks and flush pending work."""


class InMemoryEventBus(EventBus):
    """In-process event bus used for tests and local dev.

    Subscriptions run inside the same event loop as the publisher.
    Handlers may be sync or async; async handlers are awaited inline.
    Errors are routed to the subscription's DLQ (if any); otherwise
    they propagate.
    """

    def __init__(self) -> None:
        # topic -> ordered list of handlers
        self._subscriptions: dict[str, list[EventHandler]] = defaultdict(list)
        self._next_sub_id = 0
        # dlq_name -> list of events that failed handling
        self._dlqs: dict[str, list[BaseModel]] = defaultdict(list)
        self._started = False

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
        for handler in list(self._subscriptions.get(topic, [])):
            try:
                result = handler.handle(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                if handler.dlq:
                    # Re-publish to the DLQ. If the DLQ handler also
                    # fails, propagate that secondary failure.
                    self._dlqs[handler.dlq].append(event)
                else:
                    raise
        return str(event_id)

    def subscribe(
        self,
        topic: str,
        handler: Callable | EventHandler,
        *,
        dlq: str | None = None,
    ) -> str:
        """Register a handler. See :meth:`EventBus.subscribe`."""
        self._next_sub_id += 1
        sub_id = f"sub-{self._next_sub_id}"
        if not isinstance(handler, EventHandler):
            # Wrap a bare callable with a default name (the function's
            # ``__name__``) and the supplied DLQ.
            handler = EventHandler(name=handler.__name__, callback=handler, dlq=dlq)
        else:
            # Override the handler's DLQ if the caller specified one.
            handler = handler.model_copy(update={"dlq": dlq or handler.dlq})
        self._subscriptions[topic].append(handler)
        return sub_id

    def get_dlq(self, dlq_name: str) -> list[BaseModel]:
        """Return the events currently parked in a DLQ.

        Tests use this to assert that a misbehaving handler caused the
        expected DLQ traffic. The list is a copy; mutating it does
        not affect the bus.
        """
        return list(self._dlqs.get(dlq_name, []))

    def reset(self) -> None:
        """Drop every subscription and DLQ entry.

        Useful in test setup helpers.
        """
        self._subscriptions.clear()
        self._dlqs.clear()
        self._next_sub_id = 0

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False


_BUS_SINGLETON: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the singleton in-process event bus.

    Cloud adapters are selected via the cloud profile at deploy time;
    in tests we always use the in-memory bus. Use
    :func:`reset_event_bus` between tests for isolation.
    """
    global _BUS_SINGLETON
    if _BUS_SINGLETON is None:
        _BUS_SINGLETON = InMemoryEventBus()
    return _BUS_SINGLETON


def reset_event_bus() -> None:
    """Clear the singleton event bus (for tests)."""
    global _BUS_SINGLETON
    if isinstance(_BUS_SINGLETON, InMemoryEventBus):
        _BUS_SINGLETON.reset()
    _BUS_SINGLETON = None
