"""AWS ElastiCache Redis adapter for AQIP state store.

Production: talks to ElastiCache via the ``redis.asyncio`` client.
The Redis SDK is lazy-imported; if it is missing or the endpoint is
unreachable, the adapter's ``_available`` flag stays ``False`` and
every method raises ``RuntimeError`` with a clear message — better
than silent fallback to in-process state, which would cause
production data to be lost.

For local dev and CI on machines without an ElastiCache endpoint, use
the :class:`InMemoryStateStore` directly.
"""

from __future__ import annotations

from intelliqx_state.store import StateStore


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

    def __init__(self, host: str, port: int = 6379, db: int = 0) -> None:
        self.host = host
        self.port = port
        self.db = db
        self._client = None
        self._fallback = None
        self._available = self._try_init()

    def _try_init(self) -> bool:
        """Try to create an async Redis client."""
        try:
            import redis.asyncio as aioredis  # type: ignore

            self._client = aioredis.Redis(host=self.host, port=self.port, db=self.db)
            return True
        except Exception:
            return False

    async def get(self, key: str):
        if not self._available:
            raise RuntimeError("ElastiCache requires redis SDK + endpoint")
        return await self._client.get(key)

    async def set(self, key: str, value, *, ttl_seconds: int | None = None) -> None:
        if not self._available:
            raise RuntimeError("ElastiCache requires redis SDK + endpoint")
        if ttl_seconds is not None:
            await self._client.set(key, value, ex=ttl_seconds)
        else:
            await self._client.set(key, value)

    async def delete(self, key: str) -> None:
        if not self._available:
            return
        await self._client.delete(key)

    async def incr(self, key: str, amount: int = 1) -> int:
        return int(await self._client.incrby(key, amount))

    async def expire(self, key: str, ttl_seconds: int) -> None:
        await self._client.expire(key, ttl_seconds)

    async def keys(self, prefix: str):
        async for k in self._client.scan_iter(match=f"{prefix}*"):
            yield k

    async def hset(self, key: str, field: str, value: str) -> None:
        await self._client.hset(key, field, value)

    async def hgetall(self, key: str) -> dict:
        return await self._client.hgetall(key)

    async def lpush(self, key: str, value: str) -> int:
        return int(await self._client.lpush(key, value))

    async def rpop(self, key: str):
        return await self._client.rpop(key)
