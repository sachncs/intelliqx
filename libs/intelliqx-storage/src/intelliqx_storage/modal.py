"""Modal ``Volume`` adapter for IntelliqX object store.

A Modal Volume is a filesystem-backed, read-write blob mount that
persists across function invocations within a Modal app. The
adapter writes files into a local mount directory; Modal handles
persistence and replication.

Error handling pattern (``try_init`` / ``available``):

* ``try_init`` catches ``(ImportError, OSError)``. ``ImportError``
  covers the absence of the ``modal`` SDK. ``OSError`` covers the
  case where the SDK is installed but ``Volume.from_name`` fails
  (e.g. invalid ``MODAL_TOKEN_ID``, network error reaching the
  Modal API, or a volume name that doesn't exist and
  ``create_if_missing`` is denied by permissions).
* When ``try_init`` returns ``False``, write/read methods raise
  ``RuntimeError`` while ``exists`` and ``list`` return safe no-ops.
  This is **graceful degradation** — Modal-less CI and local dev
  keep working for the rest of the platform.
* When ``try_init`` returns ``True`` but the volume is
  misconfigured at call time (e.g. the mount path is read-only),
  errors propagate loudly. Silent fallback would lose data.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from intelliqx_core.errors import NotFoundError

from intelliqx_storage.base import ObjectStore


class ModalVolumeObjectStore(ObjectStore):
    """modal.Volume-backed object store.

    Args:
        volume_name: Modal volume name.
        mount_path: Local mount path. Defaults to
            ``/mnt/{volume_name}`` (the Modal convention). For local
            testing, override to a writable directory.
    """

    def __init__(self, volume_name: str, mount_path: str | None = None) -> None:
        self.volume_name = volume_name
        self.mount_path = Path(mount_path or f"/mnt/{volume_name}")
        self.volume: Any = None
        self.available = self.try_init()

    def try_init(self) -> bool:
        try:
            import modal  # type: ignore

            self.volume = modal.Volume.from_name(self.volume_name, create_if_missing=True)
            return True
        except (ImportError, OSError):
            return False

    def path(self, key: str) -> Path:
        if key.startswith("/"):
            key = key[1:]
        return self.mount_path / key

    async def put(
        self,
        key: str,
        value: bytes,
        metadata: dict[str, Any] | None = None,
        *,
        content_type: str | None = None,
    ) -> str:
        """Write ``value`` to ``key`` in the Modal Volume.

        Creates parent directories automatically. Commits the volume
        after writing so the persisted snapshot reflects the change.

        Args:
            key: The object key.
            value: The bytes to write.
            metadata: Accepted for interface compatibility.
            content_type: Accepted for interface compatibility; Modal
                Volumes don't store MIME types.

        Returns:
            A ``modal://{volume_name}/{key}`` URI string.

        Raises:
            RuntimeError: If the Modal SDK or token is missing.
        """
        if not self.available:
            raise RuntimeError("ModalVolumeObjectStore requires modal SDK + token")
        p = self.path(key)
        # Create parent directories so nested keys work.
        p.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(p.write_bytes, value)
        # Volume commit flushes writes to the persisted snapshot.
        await asyncio.to_thread(self.volume.commit)
        return f"modal://{self.volume_name}/{key}"

    async def get(self, key: str) -> bytes:
        """Read the bytes stored at ``key``.

        Args:
            key: The object key.

        Returns:
            The stored bytes.

        Raises:
            NotFoundError: If the key does not exist on disk.
            RuntimeError: If the Modal SDK or token is missing.
        """
        if not self.available:
            raise RuntimeError("ModalVolumeObjectStore requires modal SDK + token")
        p = self.path(key)
        if not p.exists():
            raise NotFoundError(f"Object not found: {key!r}")
        return await asyncio.to_thread(p.read_bytes)

    async def exists(self, key: str) -> bool:
        """Check whether ``key`` exists on the volume mount.

        Args:
            key: The object key.

        Returns:
            True if the file exists at the resolved path.
        """
        if not self.available:
            return False
        return self.path(key).exists()

    async def delete(self, key: str) -> None:
        """Delete ``key`` from the volume mount and commit the change."""
        if not self.available:
            return
        p = self.path(key)
        if p.exists():
            await asyncio.to_thread(p.unlink)
            # Commit the deletion so the persisted snapshot reflects it.
            await asyncio.to_thread(self.volume.commit)

    async def list(self, prefix: str) -> AsyncIterator[str]:
        """Yield every file path under ``prefix`` on the volume.

        Args:
            prefix: Key prefix to filter by.

        Yields:
            Relative file path strings.
        """
        if not self.available:
            return
        if prefix.startswith("/"):
            prefix = prefix[1:]
        base = self.mount_path / prefix
        if not base.exists():
            return
        for p in sorted(base.rglob("*")):
            if p.is_file():
                yield str(p.relative_to(self.mount_path))
