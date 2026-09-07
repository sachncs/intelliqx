"""Base interface for object storage backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class ObjectStore(ABC):
    """Abstract interface implemented by every object storage backend."""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def put(
        self,
        key: str,
        value: bytes,
        metadata: dict[str, Any] | None = None,
        *,
        content_type: str | None = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def list(self, prefix: str) -> AsyncIterator[str]:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, key: str) -> bool:
        raise NotImplementedError

    async def size(self, key: str) -> int:
        return len(await self.get(key))
