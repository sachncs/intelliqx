"""Modal Queue adapter for IntelliqX event bus.

Each event topic maps to a named ``modal.Queue``. The Modal SDK is
lazy-imported; when it is missing the adapter falls back to an
in-process fan-out table, which keeps tests and CI on Modal-less
machines working.

Error handling pattern (``try_init`` / ``available``):

* ``try_init`` catches ``(ImportError, OSError)``. ``ImportError``
  covers the absence of the ``modal`` SDK. ``OSError`` covers
  failures when importing the Modal module (e.g. a corrupted
  installation or platform-specific binary issue).
* When ``try_init`` returns ``False``, ``publish`` falls through
  to the in-process fan-out table using ``subscriptions`` (or an
  explicit ``fallback`` bus). This is **graceful degradation** —
  Modal-less CI and local dev keep working.
* The ``uses_modal`` property combines ``available`` with the
  absence of an explicit ``fallback``. When a fallback is provided,
  the adapter delegates to it even if Modal is available.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from intelliqx_events.bus import EventBus
from intelliqx_events.handler import EventHandler


class ModalQueueBus(EventBus):
    """Modal Queue-backed event bus with in-memory fallback.

    Args:
        fallback: Optional explicit in-memory bus to use when Modal
            is unavailable.
    """

    def __init__(self, fallback: EventBus | None = None) -> None:
        # topic -> modal.Queue handle (populated lazily on first use)
        self.queues: dict[str, Any] = {}
        self.subscriptions: dict[str, list[EventHandler]] = {}
        self.fallback = fallback
        self.available = self.try_init()

    def try_init(self) -> bool:
        """Try to import the Modal SDK.

        Returns:
            ``True`` if Modal is importable.
        """
        try:
            import modal  # type: ignore

            self.modal = modal
            return True
        except (ImportError, OSError):
            self.modal = None
            return False

    @property
    def uses_modal(self) -> bool:
        """Return ``True`` when the Modal path is active."""
        return self.available and self.fallback is None

    def get_queue(self, topic: str) -> Any:
        """Return the modal.Queue for ``topic``, creating it if needed.

        ``modal.Queue.from_name(..., create_if_missing=True)`` returns
        a handle without network I/O; the queue is provisioned on
        first ``put``/``get``.
        """
        if topic not in self.queues:
            self.queues[topic] = self.modal.Queue.from_name(
                f"intelliqx-{topic}", create_if_missing=True
            )
        return self.queues[topic]

    async def publish(self, topic: str, event: BaseModel) -> str:
        """Push the event to the modal.Queue for ``topic``.

        In dev mode this falls through to the in-process fan-out
        table.
        """
        if not self.uses_modal:
            for handler in list(self.subscriptions.get(topic, [])):
                try:
                    res = handler.handle(event)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    if handler.dlq:
                        await self.publish(handler.dlq, event)
                    else:
                        raise
            return getattr(getattr(event, "metadata", None), "event_id", "local")
        # Production: enqueue to modal.Queue (synchronous call)
        queue = self.get_queue(topic)
        await asyncio.to_thread(queue.put, event.model_dump(mode="json"))
        return event.metadata.event_id  # type: ignore[attr-defined]

    def subscribe(
        self, topic: str, handler: Callable | EventHandler, *, dlq: str | None = None
    ) -> str:
        """Register a handler.

        Modal delivery is via ``modal.Queue``'s ``get()`` loop, not the
        in-process table, but the table is kept for dev introspection.
        """
        if not isinstance(handler, EventHandler):
            handler = EventHandler(name=handler.__name__, callback=handler, dlq=dlq)
        else:
            handler = handler.model_copy(update={"dlq": dlq or handler.dlq})
        self.subscriptions.setdefault(topic, []).append(handler)
        return f"modal-{topic}-{len(self.subscriptions[topic])}"

    async def start(self) -> None:
        """No-op: Modal delivery is pull-based via ``Queue.get()``."""
        pass

    async def stop(self) -> None:
        """No-op: Modal delivery is pull-based via ``Queue.get()``."""
        pass
