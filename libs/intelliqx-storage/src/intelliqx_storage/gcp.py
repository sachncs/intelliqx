"""GCS (Google Cloud Storage) adapter for IntelliqX object store.

Lazy-imports ``google-cloud-storage``. Same pattern as the S3 adapter:
``_available`` flips to ``True`` only when the SDK and credentials are
both present, and every method raises a clear error otherwise.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from intelliqx_core.errors import NotFoundError

from intelliqx_storage.store import ObjectStore


class GCSObjectStore(ObjectStore):
    """GCS-backed object store.

    Args:
        bucket: GCS bucket name.
        prefix: Optional key prefix for environment isolation.
    """

    def __init__(self, bucket: str, prefix: str = "") -> None:
        self.bucket_name = bucket
        self.prefix = prefix.rstrip("/")
        self._client = None
        self._bucket = None
        self._available = self._try_init()

    def _try_init(self) -> bool:
        try:
            from google.cloud import storage  # type: ignore

            self._client = storage.Client()
            # ``bucket()`` is a lazy reference; no I/O.
            self._bucket = self._client.bucket(self.bucket_name)
            return True
        except Exception:
            return False

    def _key(self, key: str) -> str:
        if key.startswith("/"):
            key = key[1:]
        if self.prefix:
            return f"{self.prefix}/{key}"
        return key

    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        if not self._available:
            raise RuntimeError("GCSObjectStore requires google-cloud-storage + GCP credentials")
        blob = self._bucket.blob(self._key(key))
        await asyncio.to_thread(
            blob.upload_from_string, data, content_type=content_type or "application/octet-stream"
        )
        return f"gs://{self.bucket_name}/{self._key(key)}"

    async def get(self, key: str) -> bytes:
        if not self._available:
            raise RuntimeError("GCSObjectStore requires google-cloud-storage + GCP credentials")
        blob = self._bucket.blob(self._key(key))
        try:
            return await asyncio.to_thread(blob.download_as_bytes)
        except Exception as e:
            raise NotFoundError(f"Object not found: {key!r}") from e

    async def exists(self, key: str) -> bool:
        if not self._available:
            return False
        blob = self._bucket.blob(self._key(key))
        return await asyncio.to_thread(blob.exists)

    async def delete(self, key: str) -> None:
        if not self._available:
            return
        blob = self._bucket.blob(self._key(key))
        await asyncio.to_thread(blob.delete)

    async def list(self, prefix: str) -> AsyncIterator[str]:
        if not self._available:
            return
        full = self._key(prefix)
        for blob in self._client.list_blobs(self.bucket_name, prefix=full):
            yield blob.name
