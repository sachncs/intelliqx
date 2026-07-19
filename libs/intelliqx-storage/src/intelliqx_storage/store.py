"""Object store interface and in-memory / filesystem implementations.

The :class:`ObjectStore` interface is intentionally minimal — just
the five methods the platform actually uses.

Implementations:

* :class:`InMemoryObjectStore` — process-local. The default for tests.
* :class:`LocalFileSystemObjectStore` — root directory on local disk.
  Useful for integration tests that need persistence across
  processes.

Both store **opaque bytes**; encoding is the caller's
responsibility. ``content_type`` is preserved by every implementation
that supports it.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from intelliqx_core.errors import NotFoundError

from intelliqx_storage.base import ObjectStore

__all__ = [
    "STORAGE_BACKEND_REGISTRY",
    "InMemoryObjectStore",
    "LocalFileSystemObjectStore",
    "get_object_store",
    "list_storage_backends",
    "register_storage_backend",
    "reset_object_store",
    "set_object_store",
]


class InMemoryObjectStore(ObjectStore):
    """In-memory object store for tests.

    Not thread-safe across processes; safe for concurrent use from
    many async tasks within one process. The optional ``put_sync``
    method allows writes from constructors that run before an event
    loop exists (e.g. inside an early init path that needs to write
    before any event loop runs).
    """

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.meta: dict[str, dict[str, Any]] = {}

    async def put(
        self,
        key: str,
        value: bytes,
        metadata: dict[str, Any] | None = None,
        *,
        content_type: str | None = None,
    ) -> str:
        self.store[key] = value
        self.meta[key] = dict(metadata or {})
        self.meta[key].setdefault("content_type", content_type)
        self.meta[key]["size"] = len(value)
        return f"mem-{len(self.store)}"

    def put_sync(
        self,
        key: str,
        value: bytes,
        metadata: dict[str, Any] | None = None,
        *,
        content_type: str | None = None,
    ) -> str:
        """Sync version of :meth:`put` for use outside an event loop.

        Used during object-store initialisation when an early init
        path needs to write its initial state before any loop runs.
        """
        self.store[key] = value
        self.meta[key] = dict(metadata or {})
        self.meta[key].setdefault("content_type", content_type)
        self.meta[key]["size"] = len(value)
        return f"mem-{len(self.store)}"

    async def get(self, key: str) -> bytes:
        if key not in self.store:
            raise NotFoundError(f"Object not found: {key!r}")
        return self.store[key]

    async def exists(self, key: str) -> bool:
        return key in self.store

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)
        self.meta.pop(key, None)

    async def list(self, prefix: str) -> AsyncIterator[str]:
        for k in sorted(self.store.keys()):
            if k.startswith(prefix):
                yield k

    def reset(self) -> None:
        """Drop every entry. Used by tests for isolation."""
        self.store.clear()
        self.meta.clear()


class LocalFileSystemObjectStore(ObjectStore):
    """Filesystem-backed object store for local dev.

    Keys are interpreted as paths relative to ``root``. Leading ``"/"``
    is stripped to keep keys portable across the two local
    implementations. All blocking I/O is offloaded to a worker thread.

    Args:
        root: Local directory to use. Created on first use if it
            doesn't exist.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        """Translate a logical key to an absolute ``Path``.

        Leading ``"/"`` is stripped so the same key produces the same
        layout on every OS.
        """
        if key.startswith("/"):
            key = key[1:]
        return self.root / key

    async def put(
        self,
        key: str,
        value: bytes,
        metadata: dict[str, Any] | None = None,
        *,
        content_type: str | None = None,
    ) -> str:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # ``asyncio.to_thread`` keeps the event loop responsive
        # even for large writes.
        await asyncio.to_thread(path.write_bytes, value)
        return f"local-{path.stat().st_size}"

    async def get(self, key: str) -> bytes:
        path = self.path(key)
        if not path.exists():
            raise NotFoundError(f"Object not found: {key!r}")
        return await asyncio.to_thread(path.read_bytes)

    async def exists(self, key: str) -> bool:
        return self.path(key).exists()

    async def delete(self, key: str) -> None:
        path = self.path(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    async def list(self, prefix: str) -> AsyncIterator[str]:
        if prefix.startswith("/"):
            prefix = prefix[1:]
        base = self.root / prefix
        if not base.exists():
            return
        for p in sorted(base.rglob("*")):
            if p.is_file():
                yield str(p.relative_to(self.root))


SINGLETON: ObjectStore | None = None

STORAGE_BACKEND_REGISTRY: dict[str, Callable[..., ObjectStore]] = {"memory": InMemoryObjectStore}


def register_storage_backend(name: str, factory: Callable[..., ObjectStore]) -> None:
    """Register or replace an object storage backend."""
    STORAGE_BACKEND_REGISTRY[name] = factory


def list_storage_backends() -> tuple[str, ...]:
    """Return registered backend names in sorted order."""
    return tuple(sorted(STORAGE_BACKEND_REGISTRY))


register_storage_backend("fs", LocalFileSystemObjectStore)


def get_object_store() -> ObjectStore:
    """Return the configured object-store singleton."""
    global SINGLETON
    if SINGLETON is not None:
        return SINGLETON

    backend_spec = os.environ.get("INTELLIQX_OBJECT_STORE", "memory")
    backend_name, separator, argument = backend_spec.partition(":")
    factory = STORAGE_BACKEND_REGISTRY.get(backend_name)
    if factory is None:
        available = ", ".join(list_storage_backends())
        raise RuntimeError(
            f"Storage backend {backend_name!r} not registered. Available backends: {available}."
        )

    SINGLETON = factory(argument) if separator else factory()
    return SINGLETON


def reset_object_store() -> None:
    """Clear the singleton object store (for tests)."""
    global SINGLETON
    SINGLETON = None


def set_object_store(store: ObjectStore) -> None:
    """Replace the singleton object store (for tests and bootstrap)."""
    global SINGLETON
    SINGLETON = store
