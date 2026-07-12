"""GCP Memorystore Redis adapter for IntelliqX state store.

Same protocol as :class:`intelliqx_state.aws.ElastiCacheStateStore`; the only
difference is the configuration: Memorystore Redis uses the GCP
project for IAM rather than AWS IAM, but the Redis protocol is
identical. The adapter does not abstract the IAM layer; the caller
is responsible for the GCP service account attached to the
deployment.
"""

from __future__ import annotations

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
        self._client = None
        self._available = self._try_init()

    def _try_init(self) -> bool:
        try:
            import redis.asyncio as aioredis  # type: ignore

            self._client = aioredis.Redis(host=self.host, port=self.port, db=self.db)
            return True
        except Exception:
            return False

    async def get(self, key: str):
        if not self._available:
            raise RuntimeError("Memorystore requires redis SDK + endpoint")
        return await self._client.get(key)

    async def set(self, key: str, value, *, ttl_seconds: int | None = None) -> None:
        if not self._available:
            raise RuntimeError("Memorystore requires redis SDK + endpoint")
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
