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

import asyncio
import os
import time
from collections.abc import AsyncIterator

from intelliqx_state.base import StateBackend as StateBackend
from intelliqx_state.base import StateStore as StateStore


class InMemoryStateStore(StateStore):
    """In-memory state store used for tests and local dev.

    Thread-safety: safe for concurrent use from many async tasks in
    a single event loop. The internal lock is *not* thread-safe across
    OS threads; if you need that, use the Redis adapter.
    """

    def __init__(self) -> None:
        self.kv: dict[str, bytes] = {}
        # expiry[key] = wall-clock absolute deadline
        self.expiry: dict[str, float] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.lists: dict[str, list[str]] = {}
        self.lock = asyncio.Lock()

    def expired(self, key: str) -> bool:
        """Return True if ``key`` has an expiry deadline that has passed."""
        exp = self.expiry.get(key)
        return exp is not None and exp <= time.time()

    async def get(self, key: str) -> bytes | None:
        async with self.lock:
            if self.expired(key):
                # Lazy eviction on access so the in-memory store
                # doesn't leak expired entries indefinitely.
                self.kv.pop(key, None)
                self.expiry.pop(key, None)
                return None
            return self.kv.get(key)

    async def set(self, key: str, value: bytes, *, ttl_seconds: int | None = None) -> None:
        async with self.lock:
            self.kv[key] = value
            if ttl_seconds is not None:
                self.expiry[key] = time.time() + ttl_seconds
            else:
                # Setting without a TTL clears any previous expiry.
                self.expiry.pop(key, None)

    async def delete(self, key: str) -> None:
        async with self.lock:
            # Delete from all four maps so a stale hash or list
            # entry can never outlive its KV key.
            self.kv.pop(key, None)
            self.expiry.pop(key, None)
            self.hashes.pop(key, None)
            self.lists.pop(key, None)

    async def incr(self, key: str, amount: int = 1) -> int:
        async with self.lock:
            cur = int(self.kv.get(key, b"0"))
            cur += amount
            self.kv[key] = str(cur).encode("utf-8")
            return cur

    async def expire(self, key: str, ttl_seconds: int) -> None:
        async with self.lock:
            self.expiry[key] = time.time() + ttl_seconds

    async def keys(self, prefix: str) -> AsyncIterator[str]:
        # Snapshot under the lock; iterate outside so we don't hold
        # the lock across the yield.
        async with self.lock:
            snapshot = [k for k in self.kv if not self.expired(k)]
        for k in snapshot:
            if k.startswith(prefix):
                yield k

    async def hset(self, key: str, field: str, value: str) -> None:
        async with self.lock:
            self.hashes.setdefault(key, {})[field] = value

    async def hgetall(self, key: str) -> dict[str, str]:
        async with self.lock:
            return dict(self.hashes.get(key, {}))

    async def hkeys(self, key: str) -> list[str]:
        async with self.lock:
            return list(self.hashes.get(key, {}))

    async def lpush(self, key: str, value: str) -> int:
        async with self.lock:
            self.lists.setdefault(key, []).insert(0, value)
            return len(self.lists[key])

    async def rpop(self, key: str) -> str | None:
        async with self.lock:
            lst = self.lists.get(key)
            if not lst:
                return None
            return lst.pop()

    def reset(self) -> None:
        """Drop every entry.

        Tests call this to keep state isolated between cases.
        """
        self.kv.clear()
        self.expiry.clear()
        self.hashes.clear()
        self.lists.clear()


SINGLETON: StateStore | None = None


STATE_BACKEND_REGISTRY: dict[str, type[StateStore]] = {
    "memory": InMemoryStateStore,
}


def register_state_backend(name: str, factory: type[StateStore]) -> None:
    """Register or replace a state backend factory."""
    STATE_BACKEND_REGISTRY[name] = factory


def _load_default_state_backends() -> None:
    """Load built-in cloud backend classes when they are importable."""
    if "aws" not in STATE_BACKEND_REGISTRY:
        try:
            from intelliqx_state.aws import ElastiCacheStateStore

            STATE_BACKEND_REGISTRY["aws"] = ElastiCacheStateStore
        except ImportError:
            pass
    if "gcp" not in STATE_BACKEND_REGISTRY:
        try:
            from intelliqx_state.gcp import MemorystoreStateStore

            STATE_BACKEND_REGISTRY["gcp"] = MemorystoreStateStore
        except ImportError:
            pass
    if "modal" not in STATE_BACKEND_REGISTRY:
        try:
            from intelliqx_state.modal import ModalDictStateStore

            STATE_BACKEND_REGISTRY["modal"] = ModalDictStateStore
        except ImportError:
            pass


def list_state_backends() -> tuple[str, ...]:
    """Return the names of all registered state backends."""
    return tuple(sorted(STATE_BACKEND_REGISTRY))


def get_state_store() -> StateStore:
    """Return the configured singleton state store."""
    global SINGLETON
    if SINGLETON is None:
        backend = os.environ.get("INTELLIQX_STATE_BACKEND", "memory")
        _load_default_state_backends()
        factory = STATE_BACKEND_REGISTRY.get(backend)
        if factory is None:
            available = ", ".join(list_state_backends())
            raise RuntimeError(
                f"State backend {backend!r} not registered. "
                f"Available backends: {available}. "
                "Use INTELLIQX_STATE_BACKEND=memory for tests/dev."
            )
        SINGLETON = factory()
    return SINGLETON


def reset_state_store() -> None:
    """Reset and clear the singleton state store."""
    global SINGLETON
    if SINGLETON is not None:
        SINGLETON.reset()
    SINGLETON = None
