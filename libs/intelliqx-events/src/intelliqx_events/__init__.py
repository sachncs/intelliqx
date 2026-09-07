"""Event bus abstraction for IntelliqX.

The platform's cross-agent backbone. The :class:`EventBus` interface
is intentionally small — ``publish`` and ``subscribe`` plus lifecycle
hooks — and is currently implemented by:

* :class:`InMemoryEventBus` — same-process pub/sub used in tests and
  in local dev mode.

Pub/Sub semantics: every event goes to every subscriber of its topic;
ordering is best-effort; delivery is best-effort with handler errors
routed to the subscription's DLQ when one is configured via
``subscribe(..., dlq="topic.dlq")``.
"""

from intelliqx_events.base import EventBus
from intelliqx_events.bus import (
    EVENT_BUS_REGISTRY,
    InMemoryEventBus,
    get_event_bus,
    list_event_bus_backends,
    register_event_bus_backend,
)
from intelliqx_events.handler import EventHandler
from intelliqx_events.schemas import EventContract, EventRegistry, get_registry

__all__ = [
    "EVENT_BUS_REGISTRY",
    "EventBus",
    "EventContract",
    "EventHandler",
    "EventRegistry",
    "InMemoryEventBus",
    "get_event_bus",
    "get_registry",
    "list_event_bus_backends",
    "register_event_bus_backend",
]
