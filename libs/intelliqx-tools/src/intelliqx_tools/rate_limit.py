"""Async token-bucket rate limiter, per-key.

The limiter is a classic token bucket: each key has a capacity
(``rate_per_minute``) and refills at a constant rate. ``acquire`` is
cooperative — if no token is available, the coroutine sleeps for
``10ms`` and tries again. This keeps a single slow tool from blocking
the rest of the agent.

Complexity:
    * :meth:`acquire` is ``O(1)`` amortised. The constant is small
      (one lock acquire per attempt; typical wait is 0-2 attempts).
    * Memory is ``O(K)`` where ``K`` is the number of distinct keys.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any


class RateLimiter:
    """Async token-bucket rate limiter, per-key.

    The implementation uses a single ``asyncio.Lock`` to serialize
    bucket updates. This is correct (token-bucket requires atomic
    read-modify-write) and fast in practice because the critical
    section is just a few arithmetic operations.
    """

    __slots__ = ("buckets", "lock")

    def __init__(self) -> None:
        # key -> {"tokens": float, "last_refill": float (monotonic)}
        self.buckets: dict[str, dict[str, float]] = defaultdict(
            lambda: {"tokens": 0.0, "last_refill": time.monotonic()}
        )
        self.lock = asyncio.Lock()

    async def acquire(self, key: str, rate_per_minute: int) -> None:
        """Block until a token is available for ``key``.

        Args:
            key: The bucket key (typically the tool name).
            rate_per_minute: Capacity and refill rate (tokens per
                minute). For example, ``60`` allows 1 request/second
                sustained; bursts up to 60 requests are allowed
                after a quiet period.

        The coroutine never raises; it returns once a token has been
        deducted from the bucket.
        """
        capacity = float(rate_per_minute)
        # Tokens per second: the bucket refills smoothly.
        refill_per_sec = capacity / 60.0
        while True:
            async with self.lock:
                b = self.buckets[key]
                now = time.monotonic()
                elapsed = now - b["last_refill"]
                # Cap at capacity to avoid long-quiet-period bursts.
                b["tokens"] = min(capacity, b["tokens"] + elapsed * refill_per_sec)
                b["last_refill"] = now
                if b["tokens"] >= 1.0:
                    b["tokens"] -= 1.0
                    return
            # Sleep outside the lock so other keys aren't blocked.
            await asyncio.sleep(0.01)

    async def wrap(
        self,
        key: str,
        rate_per_minute: int,
        fn: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Acquire a token, then await ``fn(*args, **kwargs)``.

        Convenience helper for ad-hoc rate-limited calls outside the
        tool manager.
        """
        await self.acquire(key, rate_per_minute)
        return await fn(*args, **kwargs)
