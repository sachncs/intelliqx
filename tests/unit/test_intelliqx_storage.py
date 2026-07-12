"""Tests for aqip-storage."""

from pathlib import Path

import pytest
from intelliqx_core.errors import NotFoundError
from intelliqx_storage.store import (
    InMemoryObjectStore,
    LocalFileSystemObjectStore,
    get_object_store,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_memory_put_get():
    s = InMemoryObjectStore()
    await s.put("a/b.txt", b"hello")
    assert await s.get("a/b.txt") == b"hello"
    assert await s.exists("a/b.txt")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_memory_delete_and_missing():
    s = InMemoryObjectStore()
    await s.put("k", b"v")
    await s.delete("k")
    assert not await s.exists("k")
    with pytest.raises(NotFoundError):
        await s.get("k")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_memory_list():
    s = InMemoryObjectStore()
    await s.put("a/1", b"x")
    await s.put("a/2", b"y")
    await s.put("b/1", b"z")
    keys = [k async for k in s.list("a/")]
    assert set(keys) == {"a/1", "a/2"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_fs_roundtrip(tmp_path: Path):
    s = LocalFileSystemObjectStore(tmp_path)
    await s.put("foo/bar.bin", b"data", content_type="application/octet-stream")
    assert await s.exists("foo/bar.bin")
    assert await s.get("foo/bar.bin") == b"data"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_fs_list(tmp_path: Path):
    s = LocalFileSystemObjectStore(tmp_path)
    await s.put("dir/a.txt", b"a")
    await s.put("dir/sub/b.txt", b"b")
    keys = [k async for k in s.list("dir/")]
    assert sorted(keys) == ["dir/a.txt", "dir/sub/b.txt"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_fs_not_found(tmp_path: Path):
    s = LocalFileSystemObjectStore(tmp_path)
    with pytest.raises(NotFoundError):
        await s.get("missing")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_object_store_singleton_default(monkeypatch):
    monkeypatch.delenv("AQIP_OBJECT_STORE", raising=False)
    s = get_object_store()
    assert isinstance(s, InMemoryObjectStore)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_object_store_singleton_fs(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AQIP_OBJECT_STORE", f"fs:{tmp_path}")
    s = get_object_store()
    assert isinstance(s, LocalFileSystemObjectStore)
    await s.put("k", b"v")
    assert await s.get("k") == b"v"