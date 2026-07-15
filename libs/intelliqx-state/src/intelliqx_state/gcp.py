"""GCP Memorystore Redis adapter for IntelliqX state store.

Same protocol as :class:`intelliqx_state.aws.ElastiCacheStateStore`; the only
difference is the configuration: Memorystore Redis uses the GCP
project for IAM rather than AWS IAM, but the Redis protocol is
identical. The adapter does not abstract the IAM layer; the caller
is responsible for the GCP service account attached to the
deployment.

Error handling pattern (``try_init`` / ``available``):

* ``try_init`` catches ``(ImportError, OSError)``. ``ImportError``
  covers the absence of the ``redis`` package. ``OSError`` covers
  network-level failures during client construction (e.g. an
  unreachable Memorystore endpoint or DNS failure).
* When ``try_init`` returns ``False``, every public method raises
  ``RuntimeError`` — no silent fallback to in-process state, which
  would lose state between processes in production.
* When ``try_init`` returns ``True`` but the endpoint is
  unreachable at call time, the Redis ``ConnectionError`` propagates
  as-is so the orchestration layer can handle retries.
"""

from __future__ import annotations

from typing import Any

from intelliqx_state.store import StateStore


class MemorystoreStateStore(StateStore):
    """Memorystore Redis adapter with no implicit fallback.

    Args:
        host: Memorystore Redis host (IP or DNS).
        port: Redis port (default 6379).
        db: Redis logical database number (default 0).
    """

    def __init__(self, host: str, port: int = 6379, db: int = 0) -> None:
        self.host = host
        self.port = port
        self.db = db
        self.sdk: Any = None
        self.available = self.try_init()

    def try_init(self) -> bool:
        """Try to create an async Redis client connected to Memorystore.

        Returns:
            ``True`` if the client was created successfully, ``False``
            if the ``redis`` SDK is not installed or the endpoint is
            unreachable.
        """
        try:
            import redis.asyncio as aioredis  # type: ignore[import-not-found]

            self.sdk = aioredis.Redis(host=self.host, port=self.port, db=self.db)
            return True
        except (ImportError, OSError):
            return False

    async def get(self, key: str):
        """Fetch the value for ``key`` from Memorystore.

        Args:
            key: Storage key.

        Returns:
            The stored bytes, or ``None`` if the key does not exist.

        Raises:
            RuntimeError: If the Redis SDK is not installed or the
                endpoint is unreachable.
        """
        if not self.available:
            raise RuntimeError("Memorystore requires redis SDK + endpoint")
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
            raise RuntimeError("Memorystore requires redis SDK + endpoint")
        if ttl_seconds is not None:
            await self.sdk.set(key, value, ex=ttl_seconds)
        else:
            await self.sdk.set(key, value)

    async def delete(self, key: str) -> None:
        """Remove ``key`` from Memorystore.

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
            raise RuntimeError("Memorystore requires redis SDK + endpoint")
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
            raise RuntimeError("Memorystore requires redis SDK + endpoint")
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
            raise RuntimeError("Memorystore requires redis SDK + endpoint")
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
            raise RuntimeError("Memorystore requires redis SDK + endpoint")
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
            raise RuntimeError("Memorystore requires redis SDK + endpoint")
        return await self.sdk.hgetall(key)

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
            raise RuntimeError("Memorystore requires redis SDK + endpoint")
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
            raise RuntimeError("Memorystore requires redis SDK + endpoint")
        return await self.sdk.rpop(key)
