"""Object store interface and in-memory / filesystem implementations.

The :class:`ObjectStore` interface is intentionally minimal — just
the five methods the platform actually uses. Cloud adapters
(``aws.py``, ``gcp.py``, ``modal.py``) implement the same surface.

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

import abc
import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from intelliqx_core.errors import NotFoundError


class ObjectStore(abc.ABC):
    """Abstract object store (S3 / GCS / Modal Volume / filesystem).

    All methods are coroutines so the same interface works in async
    code paths. Implementations are free to back the methods with
    blocking I/O as long as the blocking call is offloaded via
    ``asyncio.to_thread`` (the filesystem and memory stores already
    do this).
    """

    @abc.abstractmethod
    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        """Store ``data`` at ``key``.

        Args:
            key: The object key. Leading ``"/"`` is normalised away.
            data: The bytes to store.
            content_type: Optional MIME type. Persisted by cloud
                adapters so ``GET`` responses carry it.

        Returns:
            An opaque version / ETag identifier.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def get(self, key: str) -> bytes:
        """Fetch the bytes at ``key``.

        Returns:
            The stored bytes.

        Raises:
            NotFoundError: If ``key`` does not exist.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def exists(self, key: str) -> bool:
        """Return ``True`` if ``key`` is present."""
        raise NotImplementedError

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Remove ``key``. Idempotent: deleting a missing key is a no-op."""
        raise NotImplementedError

    @abc.abstractmethod
    def list(self, prefix: str) -> AsyncIterator[str]:
        """Yield every key with the given prefix.

        Yields:
            String keys. Order is implementation-defined.
        """
        raise NotImplementedError

    async def size(self, key: str) -> int:
        """Return the size in bytes of ``key``.

        Default implementation: ``len(get(key))``. Cloud adapters
        override with a HEAD-style call to avoid downloading the body.
        """
        data = await self.get(key)
        return len(data)


class InMemoryObjectStore(ObjectStore):
    """In-memory object store for tests.

    Not thread-safe across processes; safe for concurrent use from
    many async tasks within one process. The optional ``put_sync``
    method allows writes from constructors that run before an event
    loop exists (e.g. inside the zvec index bootstrap path).
    """

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.meta: dict[str, dict[str, Any]] = {}

    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        self.store[key] = data
        self.meta[key] = {"content_type": content_type, "size": len(data)}
        return f"mem-{len(self.store)}"

    def put_sync(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        """Sync version of :meth:`put` for use outside an event loop.

        Used during object-store initialisation when the zvec index
        needs to write its initial manifest before any loop runs.
        """
        self.store[key] = data
        self.meta[key] = {"content_type": content_type, "size": len(data)}
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
    is stripped to keep keys consistent with cloud adapters. All
    blocking I/O is offloaded to a worker thread.

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

    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # ``asyncio.to_thread`` keeps the event loop responsive
        # even for large writes.
        await asyncio.to_thread(path.write_bytes, data)
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
                # Keys are stored relative to the root so callers
                # get the same form as cloud adapters return.
                yield str(p.relative_to(self.root))


SINGLETON: ObjectStore | None = None


def get_object_store() -> ObjectStore:
    """Return the configured object-store singleton.

    Resolution order:

    1. ``INTELLIQX_OBJECT_STORE`` env var — ``memory`` (default) or
       ``fs:/path/to/dir``.
    2. Otherwise, the in-memory store.

    Production deployments should set the env var to point at a
    persistent backend (S3, GCS, Modal Volume) via a cloud adapter
    in their bootstrap.
    """
    global SINGLETON
    if SINGLETON is not None:
        return SINGLETON
    override = os.environ.get("INTELLIQX_OBJECT_STORE", "memory")
    if override.startswith("fs:"):
        SINGLETON = LocalFileSystemObjectStore(override[3:])
    else:
        SINGLETON = InMemoryObjectStore()
    return SINGLETON


def reset_object_store() -> None:
    """Clear the singleton object store (for tests)."""
    global SINGLETON
    SINGLETON = None


def set_object_store(store: ObjectStore) -> None:
    """Replace the singleton object store (for tests and bootstrap)."""
    global SINGLETON
    SINGLETON = store
