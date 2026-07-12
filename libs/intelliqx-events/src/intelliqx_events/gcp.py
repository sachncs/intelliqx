"""GCP Pub/Sub adapter for IntelliqX event bus.

Uses Pub/Sub topics for fan-out and subscriptions for delivery. The
``google-cloud-pubsub`` SDK is lazy-imported; if it is missing or
credentials aren't available, the adapter falls back to an in-process
fan-out table.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable

from pydantic import BaseModel

from intelliqx_events.bus import EventBus
from intelliqx_events.handler import EventHandler


class GCPPubSubBus(EventBus):
    """GCP Pub/Sub-backed event bus with in-memory fallback.

    Args:
        project_id: GCP project id. Defaults to ``GOOGLE_CLOUD_PROJECT``
            env var, then ``"intelliqx-local"`` for dev.
        fallback: Optional explicit in-memory bus to use when the GCP
            SDK is unavailable.
    """

    def __init__(
        self,
        project_id: str | None = None,
        fallback: EventBus | None = None,
    ) -> None:
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "intelliqx-local")
        self._publisher = None
        self._subscriptions: dict[str, list[EventHandler]] = {}
        self._fallback = fallback
        self._available = self._try_init()

    def _try_init(self) -> bool:
        """Try to instantiate the Pub/Sub publisher client.

        Returns:
            ``True`` if the client was created.
        """
        try:
            from google.cloud import pubsub_v1  # type: ignore

            self._publisher = pubsub_v1.PublisherClient()
            return True
        except Exception:
            return False

    @property
    def uses_gcp(self) -> bool:
        """Return ``True`` when the GCP path is active."""
        return self._available and self._fallback is None

    async def publish(self, topic: str, event: BaseModel) -> str:
        """Publish to the Pub/Sub topic ``{project_id}/{topic}``.

        The Pub/Sub publisher returns a future that resolves to a
        message id; we wrap it in ``asyncio.wrap_future`` so the rest
        of the platform can ``await`` the publish.
        """
        if not self.uses_gcp:
            # Local fallback: in-process fan-out.
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

        topic_path = self._publisher.topic_path(self.project_id, topic)
        data = json.dumps(event.model_dump(mode="json"), default=str).encode("utf-8")
        # The boto3-style sync publisher API is wrapped in a Future;
        # we surface it as an awaitable.
        future = self._publisher.publish(topic_path, data)
        return await asyncio.wrap_future(future)

    def subscribe(
        self,
        topic: str,
        handler: Callable | EventHandler,
        *,
        dlq: str | None = None,
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
        self._subscriptions.setdefault(topic, []).append(handler)
        return f"gcp-{topic}-{len(self._subscriptions[topic])}"

    async def start(self) -> None:
        """No-op: Pub/Sub delivery is push-based."""
        pass

    async def stop(self) -> None:
        """No-op: Pub/Sub delivery is push-based."""
        pass
