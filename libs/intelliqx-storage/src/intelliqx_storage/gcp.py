"""GCS (Google Cloud Storage) adapter for IntelliqX object store.

Lazy-imports ``google-cloud-storage``. Same pattern as the S3 adapter:
``available`` flips to ``True`` only when the SDK and credentials are
both present, and every method raises a clear error otherwise.

Error handling pattern (``try_init`` / ``available``):

* ``try_init`` catches ``(ImportError, OSError)``. ``ImportError``
  covers the absence of the ``google-cloud-storage`` package.
  ``OSError`` covers credential resolution failures (e.g. missing
  ``GOOGLE_APPLICATION_CREDENTIALS``, expired service-account key,
  or an unreachable metadata server on GCE).
* When ``try_init`` returns ``False``, every public method either
  raises ``RuntimeError`` (for write/read paths) or returns a safe
  no-op (``False`` for ``exists``, empty for ``list``, silent skip
  for ``delete``). This is **graceful degradation** — the rest of
  the platform keeps working without GCS.
* When ``try_init`` returns ``True`` but the GCS endpoint is
  misconfigured, the error propagates loudly. Silent fallback
  would risk data loss in production.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from intelliqx_core.errors import NotFoundError

from intelliqx_storage.base import ObjectStore


class GCSObjectStore(ObjectStore):
    """GCS-backed object store.

    Args:
        bucket: GCS bucket name.
        prefix: Optional key prefix for environment isolation.
    """

    def __init__(self, bucket: str, prefix: str = "") -> None:
        self.bucket_name = bucket
        self.prefix = prefix.rstrip("/")
        self.client: Any = None
        self.bucket: Any = None
        self.available = self.try_init()

    def try_init(self) -> bool:
        try:
            from google.cloud import storage  # type: ignore

            self.client = storage.Client()
            # ``bucket()`` is a lazy reference; no I/O.
            self.bucket = self.client.bucket(self.bucket_name)
            return True
        except (ImportError, OSError):
            return False

    def resolve_key(self, key: str) -> str:
        if key.startswith("/"):
            key = key[1:]
        if self.prefix:
            return f"{self.prefix}/{key}"
        return key

    async def put(
        self,
        key: str,
        value: bytes,
        metadata: dict[str, Any] | None = None,
        *,
        content_type: str | None = None,
    ) -> str:
        """Upload ``value`` to GCS at ``key``.

        Offloads the blocking ``upload_from_string`` call to a worker
        thread. If ``content_type`` is not provided, defaults to
        ``application/octet-stream``.

        Args:
            key: The object key.
            value: The bytes to upload.
            metadata: Optional object metadata.
            content_type: Optional MIME type.

        Returns:
            A GCS URI string (``gs://bucket/key``).

        Raises:
            RuntimeError: If the GCS SDK or credentials are missing.
        """
        if not self.available:
            raise RuntimeError("GCSObjectStore requires google-cloud-storage + GCP credentials")
        blob = self.bucket.blob(self.resolve_key(key))
        if metadata:
            blob.metadata = {name: str(item) for name, item in metadata.items()}
        await asyncio.to_thread(
            blob.upload_from_string, value, content_type=content_type or "application/octet-stream"
        )
        return f"gs://{self.bucket_name}/{self.resolve_key(key)}"

    async def get(self, key: str) -> bytes:
        """Download the bytes stored at ``key``.

        Args:
            key: The object key.

        Returns:
            The stored bytes.

        Raises:
            NotFoundError: If the key does not exist.
            RuntimeError: If the GCS SDK or credentials are missing.
        """
        if not self.available:
            raise RuntimeError("GCSObjectStore requires google-cloud-storage + GCP credentials")
        blob = self.bucket.blob(self.resolve_key(key))
        try:
            return await asyncio.to_thread(blob.download_as_bytes)
        except Exception as e:
            raise NotFoundError(f"Object not found: {key!r}") from e

    async def exists(self, key: str) -> bool:
        """Check whether ``key`` exists via GCS ``Blob.exists()``.

        Args:
            key: The object key.

        Returns:
            True if the blob exists in the bucket.
        """
        if not self.available:
            return False
        blob = self.bucket.blob(self.resolve_key(key))
        return await asyncio.to_thread(blob.exists)

    async def delete(self, key: str) -> None:
        """Delete ``key`` from GCS (no-op when backend unavailable)."""
        if not self.available:
            return
        blob = self.bucket.blob(self.resolve_key(key))
        await asyncio.to_thread(blob.delete)

    async def list(self, prefix: str) -> AsyncIterator[str]:
        """Yield every blob name under ``prefix``.

        Args:
            prefix: Key prefix to filter by.

        Yields:
            Blob name strings.
        """
        if not self.available:
            return
        full = self.resolve_key(prefix)
        for blob in self.client.list_blobs(self.bucket_name, prefix=full):
            yield blob.name
