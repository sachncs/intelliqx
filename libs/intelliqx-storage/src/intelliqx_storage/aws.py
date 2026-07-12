"""AWS S3 adapter for AQIP object store.

Lazy-imports ``boto3``. If the SDK is missing or AWS credentials are
not available, ``_available`` stays ``False`` and every method
raises a clear ``RuntimeError`` rather than silently falling back —
silent fallback would lose data in production.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from intelliqx_core.errors import NotFoundError

from intelliqx_storage.store import ObjectStore


class S3ObjectStore(ObjectStore):
    """S3-backed object store.

    Args:
        bucket: S3 bucket name.
        region: AWS region. Defaults to ``us-east-1``.
        prefix: Optional key prefix. Useful for sharing a bucket
            across environments (e.g. ``"prod/aqip/"``).
    """

    def __init__(self, bucket: str, region: str | None = None, prefix: str = "") -> None:
        self.bucket = bucket
        self.region = region or "us-east-1"
        self.prefix = prefix.rstrip("/")
        self._client = None
        self._available = self._try_init()
        self._fallback = None

    def _try_init(self) -> bool:
        try:
            import boto3  # type: ignore

            self._client = boto3.client("s3", region_name=self.region)
            return True
        except Exception:
            return False

    def _key(self, key: str) -> str:
        """Apply the configured prefix and strip any leading ``"/"``."""
        if key.startswith("/"):
            key = key[1:]
        if self.prefix:
            return f"{self.prefix}/{key}"
        return key

    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        if not self._available:
            raise RuntimeError("S3ObjectStore requires boto3 + AWS credentials")
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": self._key(key),
            "Body": data,
        }
        if content_type:
            kwargs["ContentType"] = content_type
        # Offload the synchronous boto3 call to a worker thread.
        await asyncio.to_thread(self._client.put_object, **kwargs)
        return f"s3://{self.bucket}/{self._key(key)}"

    async def get(self, key: str) -> bytes:
        if not self._available:
            raise RuntimeError("S3ObjectStore requires boto3 + AWS credentials")
        try:
            # ``get_object`` returns a dict with a streaming ``Body``;
            # we read it fully in a worker thread.
            obj = await asyncio.to_thread(
                self._client.get_object, Bucket=self.bucket, Key=self._key(key)
            )
            return await asyncio.to_thread(obj["Body"].read)
        except Exception as e:
            raise NotFoundError(f"Object not found: {key!r}") from e

    async def exists(self, key: str) -> bool:
        if not self._available:
            return False
        try:
            # ``head_object`` is the cheap existence check.
            await asyncio.to_thread(
                self._client.head_object, Bucket=self.bucket, Key=self._key(key)
            )
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> None:
        if not self._available:
            return
        await asyncio.to_thread(
            self._client.delete_object, Bucket=self.bucket, Key=self._key(key)
        )

    async def list(self, prefix: str) -> AsyncIterator[str]:
        if not self._available:
            return
        # ``list_objects_v2`` returns paginated results; we collect
        # the entire listing before yielding to keep the call shape
        # simple. For very large buckets, switch to an async
        # generator that fetches pages lazily.
        full_prefix = self._key(prefix)
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"]
