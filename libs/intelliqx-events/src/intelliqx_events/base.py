"""Base event bus contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from pydantic import BaseModel

from intelliqx_events.handler import EventHandler


class EventBus(ABC):
    """Abstract interface implemented by every event bus backend."""

    @abstractmethod
    async def publish(self, topic: str, event: BaseModel) -> str:
        """Publish an event to a topic."""
        raise NotImplementedError

    @abstractmethod
    def subscribe(
        self, topic: str, handler: Callable | EventHandler, *, dlq: str | None = None
    ) -> str:
        """Register a handler for a topic and return its subscription id."""
        raise NotImplementedError

    @abstractmethod
    def unsubscribe(self, subscription_id: str | None = None) -> None:
        """Remove one subscription, or all subscriptions when no id is provided."""
        raise NotImplementedError

    @abstractmethod
    async def dlq(self, event: BaseModel, topic: str | None = None) -> None:
        """Send an event to a dead-letter topic."""
        raise NotImplementedError

    async def start(self) -> None:
        """Start background tasks."""
        return None

    async def stop(self) -> None:
        """Stop background tasks and flush pending work."""
        return None
