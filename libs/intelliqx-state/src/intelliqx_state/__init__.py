"""State/cache abstraction.

The platform treats short-lived state (run status, audit records,
prompt-version counters, ephemeral locks) as an in-process key/value
store today. Values are **opaque bytes** — the abstraction does not
know about JSON, Protobuf, or any other encoding.

Adapters:

* :class:`InMemoryStateStore` (default) — process-local, asyncio.Lock
  guarded. Used in tests and local dev.
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
