"""Local-backend parity tests.

Asserts that :class:`InMemoryObjectStore` and
:class:`LocalFileSystemObjectStore` satisfy the same ObjectStore
contract.
"""

from pathlib import Path

import pytest
from intelliqx_storage.store import InMemoryObjectStore, LocalFileSystemObjectStore


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_memory_store_roundtrip():
    store = InMemoryObjectStore()
    await store.put("k", b"hello")
    assert await store.get("k") == b"hello"
    assert await store.exists("k")
    await store.delete("k")
    assert not await store.exists("k")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_filesystem_store_roundtrip(tmp_path: Path):
    store = LocalFileSystemObjectStore(tmp_path)
    await store.put("k", b"hello")
    assert await store.get("k") == b"hello"
    assert await store.exists("k")
    await store.delete("k")
    assert not await store.exists("k")
