"""GCP Pub/Sub adapter for IntelliqX event bus.

Uses Pub/Sub topics for fan-out and subscriptions for delivery. The
``google-cloud-pubsub`` SDK is lazy-imported; if it is missing or
credentials aren't available, the adapter falls back to an in-process
fan-out table.

Error handling pattern (``try_init`` / ``available``):

* ``try_init`` catches ``(ImportError, OSError)``. ``ImportError``
  covers the absence of ``google-cloud-pubsub``. ``OSError`` covers
  credential resolution failures at publisher-client creation time
  (missing ``GOOGLE_APPLICATION_CREDENTIALS``, expired key, or
  unreachable metadata server on GCE).
* When ``try_init`` returns ``False``, ``publish`` falls through
  to the in-process fan-out table using ``subscriptions`` (or an
  explicit ``fallback`` bus). This is **graceful degradation** —
  local dev and CI keep working without GCP credentials.
* The ``uses_gcp`` property combines ``available`` with the
  absence of an explicit ``fallback``. When a fallback is provided,
  the adapter delegates to it even if GCP is available.
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


class GCPPubSubBus(EventBus):
    """GCP Pub/Sub-backed event bus with in-memory fallback.

    Args:
        project_id: GCP project id. Defaults to ``GOOGLE_CLOUD_PROJECT``
            env var, then ``"intelliqx-local"`` for dev.
        fallback: Optional explicit in-memory bus to use when the GCP
            SDK is unavailable.
    """

    def __init__(self, project_id: str | None = None, fallback: EventBus | None = None) -> None:
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "intelliqx-local")
        self.publisher: Any = None
        self.subscriptions: dict[str, list[EventHandler]] = {}
        self.subscription_ids: dict[str, tuple[str, EventHandler]] = {}
        self.next_subscription_id = 0
        self.fallback = fallback
        self.available = self.try_init()

    def try_init(self) -> bool:
        """Try to instantiate the Pub/Sub publisher client.

        Returns:
            ``True`` if the client was created.
        """
        try:
            from google.cloud import pubsub_v1  # type: ignore

            self.publisher = pubsub_v1.PublisherClient()
            return True
        except (ImportError, OSError):
            return False

    @property
    def uses_gcp(self) -> bool:
        """Return ``True`` when the GCP path is active."""
        return self.available and self.fallback is None

    async def publish(self, topic: str, event: BaseModel) -> str:
        """Publish to the Pub/Sub topic ``{project_id}/{topic}``.

        The Pub/Sub publisher returns a future that resolves to a
        message id; we wrap it in ``asyncio.wrap_future`` so the rest
        of the platform can ``await`` the publish.
        """
        if not self.uses_gcp:
            # Local fallback: in-process fan-out.
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
            return getattr(getattr(event, "metadata", None), "event_id", "local")

        topic_path = self.publisher.topic_path(self.project_id, topic)
        data = json.dumps(event.model_dump(mode="json"), default=str).encode("utf-8")
        # The boto3-style sync publisher API is wrapped in a Future;
        # we surface it as an awaitable.
        future = self.publisher.publish(topic_path, data)
        return await asyncio.wrap_future(future)

    def subscribe(
        self, topic: str, handler: Callable | EventHandler, *, dlq: str | None = None
    ) -> str:
        """Register a handler.

        Pub/Sub delivery is push-based via subscriptions, so the
        in-process table is dev-only. It is still maintained so
        ``get_dlq``-style introspection works.
        """
        if not isinstance(handler, EventHandler):
            handler = EventHandler(name=handler.__name__, callback=handler, dlq=dlq)
        else:
            handler = handler.model_copy(update={"dlq": dlq or handler.dlq})
        self.subscriptions.setdefault(topic, []).append(handler)
        self.next_subscription_id += 1
        subscription_id = f"gcp-{topic}-{self.next_subscription_id}"
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
        """No-op: Pub/Sub delivery is push-based."""
        pass

    async def stop(self) -> None:
        """No-op: Pub/Sub delivery is push-based."""
        pass
