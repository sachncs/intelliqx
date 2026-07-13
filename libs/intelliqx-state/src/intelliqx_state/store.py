"""State store interface and in-memory implementation.

The :class:`StateStore` interface models a small subset of Redis that
covers everything IntelliqX needs: simple get/set/delete, increment, hash
fields, and list push/pop. The interface is **async-only** so callers
don't accidentally make a blocking call inside an event loop.

The :class:`InMemoryStateStore` uses a single ``asyncio.Lock`` to make
all operations atomic. The lock guards KV entries, expiry tracking,
hash maps, and list maps together so a ``set`` and a matching ``get``
are linearisable. The lock is *not* held across the body of an async
handler — only the small critical sections that touch the dicts.
"""

from __future__ import annotations

import abc
import asyncio
import time
from collections.abc import AsyncIterator


class StateStore(abc.ABC):
    """Abstract state store.

    All methods are coroutines; the in-memory implementation is fully
    async-aware. The values stored are opaque ``bytes``; encoding
    (JSON, msgpack, etc.) is the caller's responsibility.
    """

    @abc.abstractmethod
    async def get(self, key: str) -> bytes | None:
        """Return the value for ``key`` or ``None`` if missing/expired.

        Args:
            key: Storage key.

        Returns:
            The bytes value, or ``None``.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def set(self, key: str, value: bytes, *, ttl_seconds: int | None = None) -> None:
        """Store ``value`` at ``key`` with optional expiry.

        Args:
            key: Storage key.
            value: The bytes value to store.
            ttl_seconds: If set, the entry expires this many seconds
                after the current time.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Remove the key and any hash/list entries under the same name."""
        raise NotImplementedError

    @abc.abstractmethod
    async def incr(self, key: str, amount: int = 1) -> int:
        """Atomically increment an integer counter.

        Args:
            key: Counter key.
            amount: Increment size (default 1). May be negative.

        Returns:
            The new value after the increment.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def expire(self, key: str, ttl_seconds: int) -> None:
        """Set the expiry on an existing key (Redis-style)."""
        raise NotImplementedError

    @abc.abstractmethod
    def keys(self, prefix: str) -> AsyncIterator[str]:
        """Yield every non-expired key with the given prefix.

        Note: this is **O(n)** over the entire keyspace; use sparingly
        (e.g. agent startup) and prefer explicit indexes for hot paths.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def hset(self, key: str, field: str, value: str) -> None:
        """Set a single hash field under ``key``."""
        raise NotImplementedError

    @abc.abstractmethod
    async def hgetall(self, key: str) -> dict[str, str]:
        """Return all hash fields under ``key``.

        Returns:
            An empty dict if the key has no hash fields.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def lpush(self, key: str, value: str) -> int:
        """Push ``value`` to the head of the list at ``key``.

        Returns:
            The new list length.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def rpop(self, key: str) -> str | None:
        """Pop the tail of the list at ``key`` and return it, or ``None``."""
        raise NotImplementedError


class InMemoryStateStore(StateStore):
    """In-memory state store used for tests and local dev.

    Thread-safety: safe for concurrent use from many async tasks in
    a single event loop. The internal lock is *not* thread-safe across
    OS threads; if you need that, use the Redis adapter.
    """

    def __init__(self) -> None:
        self.__kv: dict[str, bytes] = {}
        # expiry[key] = wall-clock absolute deadline
        self.__expiry: dict[str, float] = {}
        self.__hashes: dict[str, dict[str, str]] = {}
        self.__lists: dict[str, list[str]] = {}
        self.__lock = asyncio.Lock()

    def _expired(self, key: str) -> bool:
        """Return True if ``key`` has an expiry deadline that has passed."""
        exp = self.__expiry.get(key)
        return exp is not None and exp <= time.time()

    async def get(self, key: str) -> bytes | None:
        async with self.__lock:
            if self._expired(key):
                # Lazy eviction on access so the in-memory store
                # doesn't leak expired entries indefinitely.
                self.__kv.pop(key, None)
                self.__expiry.pop(key, None)
                return None
            return self.__kv.get(key)

    async def set(self, key: str, value: bytes, *, ttl_seconds: int | None = None) -> None:
        async with self.__lock:
            self.__kv[key] = value
            if ttl_seconds is not None:
                self.__expiry[key] = time.time() + ttl_seconds
            else:
                # Setting without a TTL clears any previous expiry.
                self.__expiry.pop(key, None)

    async def delete(self, key: str) -> None:
        async with self.__lock:
            # Delete from all four maps so a stale hash or list
            # entry can never outlive its KV key.
            self.__kv.pop(key, None)
            self.__expiry.pop(key, None)
            self.__hashes.pop(key, None)
            self.__lists.pop(key, None)

    async def incr(self, key: str, amount: int = 1) -> int:
        async with self.__lock:
            cur = int(self.__kv.get(key, b"0"))
            cur += amount
            self.__kv[key] = str(cur).encode("utf-8")
            return cur

    async def expire(self, key: str, ttl_seconds: int) -> None:
        async with self.__lock:
            self.__expiry[key] = time.time() + ttl_seconds

    async def keys(self, prefix: str) -> AsyncIterator[str]:
        # Snapshot under the lock; iterate outside so we don't hold
        # the lock across the yield.
        async with self.__lock:
            snapshot = [k for k in self.__kv if not self._expired(k)]
        for k in snapshot:
            if k.startswith(prefix):
                yield k

    async def hset(self, key: str, field: str, value: str) -> None:
        async with self.__lock:
            self.__hashes.setdefault(key, {})[field] = value

    async def hgetall(self, key: str) -> dict[str, str]:
        async with self.__lock:
            return dict(self.__hashes.get(key, {}))

    async def lpush(self, key: str, value: str) -> int:
        async with self.__lock:
            self.__lists.setdefault(key, []).insert(0, value)
            return len(self.__lists[key])

    async def rpop(self, key: str) -> str | None:
        async with self.__lock:
            lst = self.__lists.get(key)
            if not lst:
                return None
            return lst.pop()

    def reset(self) -> None:
        """Drop every entry.

        Tests call this to keep state isolated between cases.
        """
        self.__kv.clear()
        self.__expiry.clear()
        self.__hashes.clear()
        self.__lists.clear()


_SINGLETON: StateStore | None = None


def get_state_store() -> StateStore:
    """Return the singleton in-memory state store.

    Use :func:`reset_state_store` between tests for isolation.
    """
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = InMemoryStateStore()
    return _SINGLETON


def reset_state_store() -> None:
    """Clear the singleton state store (for tests)."""
    global _SINGLETON
    if isinstance(_SINGLETON, InMemoryStateStore):
        _SINGLETON.reset()
    _SINGLETON = None
