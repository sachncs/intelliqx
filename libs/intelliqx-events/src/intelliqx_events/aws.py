"""AWS EventBridge + SQS adapter for IntelliqX event bus.

Wraps the abstract :class:`EventBus` interface with AWS EventBridge (for
fan-out) + SQS (for per-consumer buffering and DLQ) semantics.
``boto3`` is **lazy-imported** so the import succeeds without the AWS
SDK installed locally — important for fast local dev and CI on
non-AWS machines.

Production topology:

* A single custom EventBridge bus (default name ``"intelliqx.bus"``).
* One SQS queue per consumer, with an SQS DLQ wired via a redrive
  policy. Consumers poll SQS; EventBridge rules fan events out via
  SQS targets.

The adapter is intentionally minimal: no batching, no partial
batches, no native consumer. The compute runtime is responsible for
draining SQS in production.

Error handling pattern (``try_init_aws`` / ``aws_available``):

* ``try_init_aws`` catches ``(ImportError, OSError)``.
  ``ImportError`` covers the absence of ``boto3``. ``OSError``
  covers credential resolution failures at client-creation time
  (missing AWS credentials, invalid region, or network errors).
* When ``aws_available`` is ``False``, ``publish`` falls through
  to an in-process fan-out using the ``subscriptions`` table (or
  an explicit ``fallback`` bus if one was provided). This is
  **graceful degradation** — local dev and CI keep working without
  AWS credentials.
* The ``uses_aws`` property combines ``aws_available`` with the
  absence of an explicit ``fallback``. When a fallback is provided,
  the adapter delegates to it even if AWS is available, giving
  callers full control over the routing.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from intelliqx_events.base import EventBus
from intelliqx_events.handler import EventHandler


class AWSEventBridgeBus(EventBus):
    """EventBridge + SQS bus.

    Args:
        bus_name: EventBridge custom bus name.
        region: AWS region. Defaults to ``AWS_REGION`` env var, then
            ``us-east-1``.
        fallback: Optional in-memory bus used when the AWS SDK or
            credentials are missing. If unset, the adapter falls
            back to its own in-process subscription list (useful
            for local dev that still wants publish/subscribe
            behaviour).
    """

    def __init__(
        self,
        bus_name: str = "intelliqx.bus",
        region: str | None = None,
        fallback: EventBus | None = None,
    ) -> None:
        self.bus_name = bus_name
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.client: Any = None
        self.subscriptions: dict[str, list[EventHandler]] = {}
        self.subscription_ids: dict[str, tuple[str, EventHandler]] = {}
        self.next_subscription_id = 0
        self.fallback = fallback
        self.aws_available = self.try_init_aws()

    def try_init_aws(self) -> bool:
        """Try to instantiate the boto3 EventBridge client.

        Returns:
            ``True`` if the client was created; ``False`` if the SDK
            is missing or credentials aren't available.
        """
        try:
            import boto3  # type: ignore

            self.client = boto3.client("events", region_name=self.region)
            return True
        except (ImportError, OSError):
            return False

    @property
    def uses_aws(self) -> bool:
        """Return ``True`` when the AWS path is in use.

        The bus is considered "using AWS" only when the SDK is
        available *and* no explicit fallback was provided.
        """
        return self.aws_available and self.fallback is None

    async def publish(self, topic: str, event: BaseModel) -> str:
        """Publish ``event`` to ``topic`` via EventBridge.

        When AWS is unavailable, behaves as an in-process fan-out
        bus instead of raising — local dev should not need AWS
        credentials.
        """
        if not self.uses_aws:
            if self.fallback is not None:
                return await self.fallback.publish(topic, event)
            # Local: in-process fan-out using the in-memory handler
            # list. Useful for running the bus adapter without an
            # explicit fallback configured.
            for handler in list(self.subscriptions.get(topic, [])):
                try:
                    res = handler.handle(event)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    if handler.dlq:
                        await self.dlq(event, handler.dlq)
                    else:
                        raise
            return event.metadata.event_id if hasattr(event, "metadata") else "local"

        # AWS path: pack the serialised event into a single Entry
        # for ``put_events``. EventBridge limits entries to 256KB
        # each; the platform assumes events stay well under that
        # (typical: a few KB).
        entry = {
            "Source": "intelliqx",
            "DetailType": topic,
            "Detail": json.dumps(event.model_dump(mode="json"), default=str),
            "EventBusName": self.bus_name,
        }
        # The boto3 ``put_events`` call is blocking and can take a
        # few hundred ms; offload to a thread to keep the event
        # loop responsive.
        await asyncio.to_thread(self.client.put_events, Entries=[entry])
        # Return a slice of the serialised detail as a synthetic id
        # when the event id isn't recoverable (e.g. non-IntelliqX event).
        return entry["Detail"][:36]

    def subscribe(
        self, topic: str, handler: Callable | EventHandler, *, dlq: str | None = None
    ) -> str:
        """Register a handler.

        In AWS mode the in-process ``subscriptions`` table is **not**
        consulted for delivery (EventBridge is the source of truth),
        but it is still maintained so that ``get_dlq``-style
        introspection works in dev.
        """
        if not isinstance(handler, EventHandler):
            handler = EventHandler(name=handler.__name__, callback=handler, dlq=dlq)
        else:
            handler = handler.model_copy(update={"dlq": dlq or handler.dlq})
        self.subscriptions.setdefault(topic, []).append(handler)
        self.next_subscription_id += 1
        subscription_id = f"aws-{topic}-{self.next_subscription_id}"
        self.subscription_ids[subscription_id] = (topic, handler)
        return subscription_id

    def unsubscribe(self, subscription_id: str | None = None) -> None:
        """Remove a local subscription used by the fallback path."""
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
        """Route an event to the configured dead-letter topic."""
        if self.fallback is not None:
            await self.fallback.dlq(event, topic)
            return
        await self.publish(topic or "dlq", event)

    async def start(self) -> None:
        """No-op: AWS delivery is push-based via EventBridge."""
        pass

    async def stop(self) -> None:
        """No-op: AWS delivery is push-based via EventBridge."""
        pass
