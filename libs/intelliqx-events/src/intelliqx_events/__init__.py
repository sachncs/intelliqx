"""Event bus abstraction for IntelliqX.

The platform's cross-agent backbone. The :class:`EventBus` interface
is intentionally small — ``publish`` and ``subscribe`` plus lifecycle
hooks — and is implemented by:

* :class:`InMemoryEventBus` — same-process pub/sub used in tests and
  in the local dev mode.
* :class:`AWSEventBridgeBus` — EventBridge for fan-out, SQS for
  per-consumer buffering and DLQ.
* :class:`GCPPubSubBus` — Pub/Sub topics with subscriptions.
* :class:`ModalQueueBus` — modal.Queue per topic.

Pub/Sub semantics: every event goes to every subscriber of its topic;
ordering is best-effort; at-least-once delivery is the cloud
adapters' contract. Subscribers can opt into a dead-letter topic via
``subscribe(..., dlq="topic.dlq")``; failed invocations are routed
there.
"""

from intelliqx_events.bus import EventBus, InMemoryEventBus, get_event_bus
from intelliqx_events.handler import EventHandler
from intelliqx_events.schemas import EventContract, EventRegistry, get_registry

__all__ = [
    "EventBus",
    "EventContract",
    "EventHandler",
    "EventRegistry",
    "InMemoryEventBus",
    "get_event_bus",
    "get_registry",
]
