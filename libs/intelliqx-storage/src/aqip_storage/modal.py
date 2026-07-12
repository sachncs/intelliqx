"""Modal ``Volume`` adapter for AQIP object store.

A Modal Volume is a filesystem-backed, read-write blob mount that
persists across function invocations within a Modal app. The
adapter writes files into a local mount directory; Modal handles
persistence and replication.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from aqip_core.errors import NotFoundError

from aqip_storage.store import ObjectStore


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
        self._volume = None
        self._available = self._try_init()

    def _try_init(self) -> bool:
        try:
            import modal  # type: ignore

            self._volume = modal.Volume.from_name(self.volume_name, create_if_missing=True)
            return True
        except Exception:
            return False

    def _path(self, key: str) -> Path:
        if key.startswith("/"):
            key = key[1:]
        return self.mount_path / key

    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        if not self._available:
            raise RuntimeError("ModalVolumeObjectStore requires modal SDK + token")
        p = self._path(key)
        # Create parent directories so nested keys work.
        p.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(p.write_bytes, data)
        # Volume commit flushes writes to the persisted snapshot.
        await asyncio.to_thread(self._volume.commit)
        return f"modal://{self.volume_name}/{key}"

    async def get(self, key: str) -> bytes:
        if not self._available:
            raise RuntimeError("ModalVolumeObjectStore requires modal SDK + token")
        p = self._path(key)
        if not p.exists():
            raise NotFoundError(f"Object not found: {key!r}")
        return await asyncio.to_thread(p.read_bytes)

    async def exists(self, key: str) -> bool:
        if not self._available:
            return False
        return self._path(key).exists()

    async def delete(self, key: str) -> None:
        if not self._available:
            return
        p = self._path(key)
        if p.exists():
            await asyncio.to_thread(p.unlink)
            # Commit the deletion so the persisted snapshot reflects it.
            await asyncio.to_thread(self._volume.commit)

    async def list(self, prefix: str) -> AsyncIterator[str]:
        if not self._available:
            return
        if prefix.startswith("/"):
            prefix = prefix[1:]
        base = self.mount_path / prefix
        if not base.exists():
            return
        for p in sorted(base.rglob("*")):
            if p.is_file():
                yield str(p.relative_to(self.mount_path))
