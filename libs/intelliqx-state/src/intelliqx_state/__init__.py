"""State/cache abstraction (Redis-compatible).

The platform treats short-lived state (run status, audit records,
prompt-version counters, ephemeral locks) as a Redis-compatible
key/value store. Values are **opaque bytes** — the abstraction does
not know about JSON, Protobuf, or any other encoding.

Adapters:

* :class:`InMemoryStateStore` (default) — process-local, asyncio.Lock
  guarded. Used in tests and local dev.
* :class:`ElastiCacheStateStore` (AWS) — talks to ElastiCache via the
  ``redis.asyncio`` client.
* :class:`MemorystoreStateStore` (GCP) — same protocol as ElastiCache
  but aimed at Memorystore Redis.
* :class:`ModalDictStateStore` (Modal) — uses ``modal.Dict`` for
  ephemeral, in-memory-per-app state. Note: ``modal.Dict`` does not
  support TTL natively.
"""

from intelliqx_state.base import StateBackend, StateStore
from intelliqx_state.store import (
    InMemoryStateStore,
    get_state_store,
    list_state_backends,
    register_state_backend,
    reset_state_store,
)

__all__ = [
    "InMemoryStateStore",
    "StateBackend",
    "StateStore",
    "get_state_store",
    "list_state_backends",
    "register_state_backend",
    "reset_state_store",
]
