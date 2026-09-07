"""State store interfaces shared by all backend implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


class StateStore(ABC):
    """Abstract interface for asynchronous state stores."""

    @abstractmethod
    async def get(self, key: str) -> bytes | None:
        """Return the value for a key, or ``None`` when it is absent."""
        raise NotImplementedError

    @abstractmethod
    async def set(self, key: str, value: bytes, *, ttl_seconds: int | None = None) -> None:
        """Store a value with an optional expiry."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a key and its associated data."""
        raise NotImplementedError

    @abstractmethod
    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment a counter and return its new value."""
        raise NotImplementedError

    @abstractmethod
    async def expire(self, key: str, ttl_seconds: int) -> None:
        """Set the expiry for an existing key."""
        raise NotImplementedError

    @abstractmethod
    def keys(self, prefix: str) -> AsyncIterator[str]:
        """Iterate over keys with a prefix."""
        raise NotImplementedError

    @abstractmethod
    async def hset(self, key: str, field: str, value: str) -> None:
        """Set a hash field."""
        raise NotImplementedError

    @abstractmethod
    async def hgetall(self, key: str) -> dict[str, str]:
        """Return all fields and values in a hash."""
        raise NotImplementedError

    @abstractmethod
    async def hkeys(self, key: str) -> list[str]:
        """Return all field names in a hash."""
        raise NotImplementedError

    @abstractmethod
    async def lpush(self, key: str, value: str) -> int:
        """Push a value to the head of a list."""
        raise NotImplementedError

    @abstractmethod
    async def rpop(self, key: str) -> str | None:
        """Pop and return the tail value of a list."""
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Reset state maintained by the backend."""
        raise NotImplementedError


@runtime_checkable
class StateBackend(Protocol):
    """Structural state backend interface for backwards compatibility."""

    async def get(self, key: str) -> bytes | None: ...

    async def set(self, key: str, value: bytes, *, ttl_seconds: int | None = None) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def incr(self, key: str, amount: int = 1) -> int: ...

    async def expire(self, key: str, ttl_seconds: int) -> None: ...

    def keys(self, prefix: str) -> AsyncIterator[str]: ...

    async def hset(self, key: str, field: str, value: str) -> None: ...

    async def hgetall(self, key: str) -> dict[str, str]: ...

    async def hkeys(self, key: str) -> list[str]: ...

    async def lpush(self, key: str, value: str) -> int: ...

    async def rpop(self, key: str) -> str | None: ...

    def reset(self) -> None: ...
