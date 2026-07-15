"""AWS ElastiCache Redis adapter for IntelliqX state store.

Production: talks to ElastiCache via the ``redis.asyncio`` client.
The Redis SDK is lazy-imported; if it is missing or the endpoint is
unreachable, the adapter's ``available`` flag stays ``False`` and
every method raises ``RuntimeError`` with a clear message — better
than silent fallback to in-process state, which would cause
production data to be lost.

For local dev and CI on machines without an ElastiCache endpoint, use
the :class:`InMemoryStateStore` directly.

Error handling pattern (``try_init`` / ``available``):

* ``try_init`` catches ``(ImportError, OSError)``. ``ImportError``
  covers the absence of the ``redis`` package. ``OSError`` covers
  network-level failures during client construction (e.g. an
  unreachable ElastiCache endpoint, DNS resolution failure, or
  a refused connection when the security group blocks the port).
* When ``try_init`` returns ``False``, every public method raises
  ``RuntimeError`` — there is no silent fallback to in-process
  state because that would silently lose state between processes.
  This is a deliberate "fail loud" policy.
* When ``try_init`` returns ``True`` but the endpoint becomes
  unreachable at call time, the Redis ``ConnectionError`` propagates
  as-is. The caller is expected to handle transient failures
  (retries, circuit breakers) at the orchestration layer.
"""

from __future__ import annotations

import os
from typing import Any

from intelliqx_state.base import StateStore


class ElastiCacheStateStore(StateStore):
    """ElastiCache Redis-backed state store with no implicit fallback.

    Args:
        host: ElastiCache primary endpoint.
        port: Redis port (default 6379).
        db: Redis logical database number (default 0).

    Raises:
        RuntimeError: On every method call when the redis SDK is not
            installed or the endpoint is unreachable. We deliberately
            do not silently fall back to the in-memory store because
            that would lose state between processes.
    """

    def __init__(
        self, host: str | None = None, port: int | None = None, db: int | None = None
    ) -> None:
        self.host = host if host is not None else os.environ.get("REDIS_HOST", "localhost")
        self.port = port if port is not None else int(os.environ.get("REDIS_PORT", "6379"))
        self.db = db if db is not None else int(os.environ.get("REDIS_DB", "0"))
        self.sdk: Any = None
        self.available = self.try_init()

    def try_init(self) -> bool:
        """Try to create an async Redis client."""
        try:
            import redis.asyncio as aioredis  # type: ignore[import-not-found]

            self.sdk = aioredis.Redis(host=self.host, port=self.port, db=self.db)
            return True
        except (ImportError, OSError):
            return False

    async def get(self, key: str):
        """Fetch the value for ``key`` from ElastiCache.

        Args:
            key: Storage key.

        Returns:
            The stored bytes, or ``None`` if the key does not exist.

        Raises:
            RuntimeError: If the Redis SDK is not installed or the
                endpoint is unreachable.
        """
        if not self.available:
            raise RuntimeError("ElastiCache requires redis SDK + endpoint")
        return await self.sdk.get(key)

    async def set(self, key: str, value, *, ttl_seconds: int | None = None) -> None:
        """Store ``value`` at ``key`` with optional TTL.

        Args:
            key: Storage key.
            value: The value to store (bytes or str).
            ttl_seconds: If set, the entry expires after this many
                seconds. ``None`` means no expiry.

        Raises:
            RuntimeError: If the Redis SDK is not installed or the
                endpoint is unreachable.
        """
        if not self.available:
            raise RuntimeError("ElastiCache requires redis SDK + endpoint")
        if ttl_seconds is not None:
            await self.sdk.set(key, value, ex=ttl_seconds)
        else:
            await self.sdk.set(key, value)

    async def delete(self, key: str) -> None:
        """Remove ``key`` from ElastiCache.

        This is a no-op when the backend is unavailable, matching the
        idempotent delete contract of the abstract interface.

        Args:
            key: Storage key to remove.
        """
        if not self.available:
            return
        await self.sdk.delete(key)

    async def incr(self, key: str, amount: int = 1) -> int:
        """Atomically increment an integer counter at ``key``.

        Delegates to Redis ``INCRBY``. If the key does not exist, it
        is created with value ``amount``.

        Args:
            key: Counter key.
            amount: Increment size (default 1). May be negative.

        Returns:
            The new value after the increment.

        Raises:
            RuntimeError: If the Redis SDK is not installed or the
                endpoint is unreachable.
        """
        if not self.available:
            raise RuntimeError("ElastiCache requires redis SDK + endpoint")
        return int(await self.sdk.incrby(key, amount))

    async def expire(self, key: str, ttl_seconds: int) -> None:
        """Set a TTL on an existing key.

        Args:
            key: Storage key.
            ttl_seconds: Seconds until the key expires.

        Raises:
            RuntimeError: If the Redis SDK is not installed or the
                endpoint is unreachable.
        """
        if not self.available:
            raise RuntimeError("ElastiCache requires redis SDK + endpoint")
        await self.sdk.expire(key, ttl_seconds)

    async def keys(self, prefix: str):
        """Yield every key that starts with ``prefix``.

        Uses Redis ``SCAN`` iteration so the server is not blocked
        during enumeration. This is **O(n)** over the keyspace; prefer
        explicit indexes for hot paths.

        Args:
            prefix: Key prefix to match.

        Yields:
            Matching key strings.

        Raises:
            RuntimeError: If the Redis SDK is not installed or the
                endpoint is unreachable.
        """
        if not self.available:
            raise RuntimeError("ElastiCache requires redis SDK + endpoint")
        async for k in self.sdk.scan_iter(match=f"{prefix}*"):
            yield k

    async def hset(self, key: str, field: str, value: str) -> None:
        """Set a single hash field under ``key``.

        Args:
            key: The hash key.
            field: The field name within the hash.
            value: The string value to store.

        Raises:
            RuntimeError: If the Redis SDK is not installed or the
                endpoint is unreachable.
        """
        if not self.available:
            raise RuntimeError("ElastiCache requires redis SDK + endpoint")
        await self.sdk.hset(key, field, value)

    async def hgetall(self, key: str) -> dict:
        """Return all hash fields and values under ``key``.

        Args:
            key: The hash key.

        Returns:
            A ``dict[str, str]`` of all fields. Empty if the key does
            not exist or has no hash fields.

        Raises:
            RuntimeError: If the Redis SDK is not installed or the
                endpoint is unreachable.
        """
        if not self.available:
            raise RuntimeError("ElastiCache requires redis SDK + endpoint")
        return await self.sdk.hgetall(key)

    async def hkeys(self, key: str) -> list[str]:
        """Return all hash field names under ``key``."""
        if not self.available:
            raise RuntimeError("ElastiCache requires redis SDK + endpoint")
        return await self.sdk.hkeys(key)

    async def lpush(self, key: str, value: str) -> int:
        """Push ``value`` to the head of the list at ``key``.

        Args:
            key: The list key.
            value: The string value to prepend.

        Returns:
            The new list length after the push.

        Raises:
            RuntimeError: If the Redis SDK is not installed or the
                endpoint is unreachable.
        """
        if not self.available:
            raise RuntimeError("ElastiCache requires redis SDK + endpoint")
        return int(await self.sdk.lpush(key, value))

    async def rpop(self, key: str):
        """Pop and return the tail element of the list at ``key``.

        Args:
            key: The list key.

        Returns:
            The popped string value, or ``None`` if the list is empty
            or the key does not exist.

        Raises:
            RuntimeError: If the Redis SDK is not installed or the
                endpoint is unreachable.
        """
        if not self.available:
            raise RuntimeError("ElastiCache requires redis SDK + endpoint")
        return await self.sdk.rpop(key)

    def reset(self) -> None:
        """Leave remote state intact when resetting the local singleton."""
        return None
