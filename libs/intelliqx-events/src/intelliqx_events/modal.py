"""Modal Queue adapter for AQIP event bus.

Each event topic maps to a named ``modal.Queue``. The Modal SDK is
lazy-imported; when it is missing the adapter falls back to an
in-process fan-out table, which keeps tests and CI on Modal-less
machines working.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from aqip_events.bus import EventBus
from aqip_events.handler import EventHandler


class ModalQueueBus(EventBus):
    """Modal Queue-backed event bus with in-memory fallback.

    Args:
        fallback: Optional explicit in-memory bus to use when Modal
            is unavailable.
    """

    def __init__(self, fallback: EventBus | None = None) -> None:
        # topic -> modal.Queue handle (populated lazily on first use)
        self._queues: dict[str, Any] = {}
        self._subscriptions: dict[str, list[EventHandler]] = {}
        self._fallback = fallback
        self._available = self._try_init()

    def _try_init(self) -> bool:
        """Try to import the Modal SDK.

        Returns:
            ``True`` if Modal is importable.
        """
        try:
            import modal  # type: ignore

            self._modal = modal
            return True
        except Exception:
            self._modal = None
            return False

    @property
    def uses_modal(self) -> bool:
        """Return ``True`` when the Modal path is active."""
        return self._available and self._fallback is None

    def _get_queue(self, topic: str) -> Any:
        """Return the modal.Queue for ``topic``, creating it if needed.

        ``modal.Queue.from_name(..., create_if_missing=True)`` returns
        a handle without network I/O; the queue is provisioned on
        first ``put``/``get``.
        """
        if topic not in self._queues:
            self._queues[topic] = self._modal.Queue.from_name(
                f"aqip-{topic}", create_if_missing=True
            )
        return self._queues[topic]

    async def publish(self, topic: str, event: BaseModel) -> str:
        """Push the event to the modal.Queue for ``topic``.

        In dev mode this falls through to the in-process fan-out
        table.
        """
        if not self.uses_modal:
            for handler in list(self._subscriptions.get(topic, [])):
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
        queue = self._get_queue(topic)
        await asyncio.to_thread(queue.put, event.model_dump(mode="json"))
        return event.metadata.event_id

    def subscribe(
        self,
        topic: str,
        handler: Callable | EventHandler,
        *,
        dlq: str | None = None,
    ) -> str:
        """Register a handler.

        Modal delivery is via ``modal.Queue``'s ``get()`` loop, not the
        in-process table, but the table is kept for dev introspection.
        """
        if not isinstance(handler, EventHandler):
            handler = EventHandler(name=handler.__name__, callback=handler, dlq=dlq)
        else:
            handler = handler.model_copy(update={"dlq": dlq or handler.dlq})
        self._subscriptions.setdefault(topic, []).append(handler)
        return f"modal-{topic}-{len(self._subscriptions[topic])}"

    async def start(self) -> None:
        """No-op: Modal delivery is pull-based via ``Queue.get()``."""
        pass

    async def stop(self) -> None:
        """No-op: Modal delivery is pull-based via ``Queue.get()``."""
        pass
