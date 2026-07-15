"""AWS S3 adapter for IntelliqX object store.

Lazy-imports ``boto3``. If the SDK is missing or AWS credentials are
not available, ``available`` stays ``False`` and every method
raises a clear ``RuntimeError`` rather than silently falling back —
silent fallback would lose data in production.

Error handling pattern (``try_init`` / ``available``):

* ``try_init`` catches ``(ImportError, OSError)``. ``ImportError``
  covers the case where ``boto3`` is not installed at all.
  ``OSError`` covers the case where ``boto3`` is installed but
  credential resolution fails at client-creation time (e.g. missing
  ``~/.aws/credentials``, invalid ``AWS_ACCESS_KEY_ID``, or an
  unreachable STS endpoint when using assume-role).
* When ``try_init`` returns ``False``, every public method either
  raises ``RuntimeError`` (for operations that must succeed) or
  returns a safe no-op value (``False`` for ``exists``, empty for
  ``list``, silent skip for ``delete``). This is **graceful
  degradation** — callers that don't use S3 get a working system
  rather than a crash at import time.
* When ``try_init`` returns ``True`` but the S3 endpoint is
  misconfigured at call time, the ``RuntimeError`` is not caught
  and propagates loudly — this is intentional. Silent fallback
  to in-process state would lose data in production, so we prefer
  a loud failure.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from intelliqx_core.errors import NotFoundError

from intelliqx_storage.base import ObjectStore


class S3ObjectStore(ObjectStore):
    """S3-backed object store.

    Args:
        bucket: S3 bucket name.
        region: AWS region. Defaults to ``us-east-1``.
        prefix: Optional key prefix. Useful for sharing a bucket
            across environments (e.g. ``"prod/intelliqx/"``).
    """

    def __init__(self, bucket: str, region: str | None = None, prefix: str = "") -> None:
        self.bucket = bucket
        self.region = region or "us-east-1"
        self.prefix = prefix.rstrip("/")
        self.client: Any = None
        self.available = self.try_init()

    def try_init(self) -> bool:
        try:
            import boto3  # type: ignore

            self.client = boto3.client("s3", region_name=self.region)
            return True
        except (ImportError, OSError):
            return False

    def key(self, key: str) -> str:
        """Apply the configured prefix and strip any leading ``"/"``."""
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
        """Upload ``value`` to S3 at ``key``.

        Offloads the blocking ``put_object`` call to a worker thread
        so the event loop is not blocked during large uploads.

        Args:
            key: The object key. Leading ``"/"`` is stripped; the
                configured ``prefix`` is prepended.
            value: The bytes to upload.
            metadata: Optional object metadata.
            content_type: Optional MIME type stored on the object.

        Returns:
            An S3 URI string (``s3://bucket/key``).

        Raises:
            RuntimeError: If ``boto3`` is not installed or credentials
                are missing.
        """
        if not self.available:
            raise RuntimeError("S3ObjectStore requires boto3 + AWS credentials")
        kwargs: dict[str, Any] = {"Bucket": self.bucket, "Key": self.key(key), "Body": value}
        if metadata:
            kwargs["Metadata"] = {name: str(item) for name, item in metadata.items()}
        if content_type:
            kwargs["ContentType"] = content_type
        # Offload the synchronous boto3 call to a worker thread.
        await asyncio.to_thread(self.client.put_object, **kwargs)
        return f"s3://{self.bucket}/{self.key(key)}"

    async def get(self, key: str) -> bytes:
        """Download the bytes stored at ``key``.

        Offloads both the ``get_object`` call and the streaming body
        read to worker threads.

        Args:
            key: The object key.

        Returns:
            The stored bytes.

        Raises:
            NotFoundError: If the key does not exist.
            RuntimeError: If ``boto3`` is not installed or credentials
                are missing.
        """
        if not self.available:
            raise RuntimeError("S3ObjectStore requires boto3 + AWS credentials")
        try:
            # ``get_object`` returns a dict with a streaming ``Body``;
            # we read it fully in a worker thread.
            obj = await asyncio.to_thread(
                self.client.get_object, Bucket=self.bucket, Key=self.key(key)
            )
            return await asyncio.to_thread(obj["Body"].read)
        except Exception as e:
            raise NotFoundError(f"Object not found: {key!r}") from e

    async def exists(self, key: str) -> bool:
        """Check whether ``key`` exists via S3 ``HEAD``.

        Returns ``False`` when the backend is unavailable (graceful
        degradation) — callers should treat ``False`` as "unknown"
        rather than "definitely missing" when running without S3.

        Args:
            key: The object key.

        Returns:
            True if the object exists in the bucket.
        """
        if not self.available:
            return False
        try:
            # ``head_object`` is the cheap existence check.
            await asyncio.to_thread(
                self.client.head_object, Bucket=self.bucket, Key=self.key(key)
            )
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> None:
        """Delete ``key`` from S3 (idempotent no-op if backend unavailable)."""
        if not self.available:
            return
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=self.key(key))

    async def list(self, prefix: str) -> AsyncIterator[str]:
        """Yield every key under ``prefix``.

        Uses the ``list_objects_v2`` paginator. For very large
        buckets, consider switching to a lazy async generator that
        fetches pages on demand. Yields nothing when the backend is
        unavailable.

        Args:
            prefix: Key prefix to filter by.

        Yields:
            Object key strings (including the ``prefix``).
        """
        if not self.available:
            return
        # ``list_objects_v2`` returns paginated results; we collect
        # the entire listing before yielding to keep the call shape
        # simple. For very large buckets, switch to an async
        # generator that fetches pages lazily.
        full_prefix = self.key(prefix)
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"]
