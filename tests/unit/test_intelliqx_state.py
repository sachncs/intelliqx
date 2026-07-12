"""Tests for aqip-state."""

import asyncio

import pytest
from intelliqx_state.store import InMemoryStateStore, get_state_store


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_get():
    s = InMemoryStateStore()
    await s.set("k", b"v")
    assert await s.get("k") == b"v"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ttl_expiration():
    s = InMemoryStateStore()
    await s.set("k", b"v", ttl_seconds=0)
    await asyncio.sleep(0.05)
    assert await s.get("k") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_incr():
    s = InMemoryStateStore()
    assert await s.incr("c") == 1
    assert await s.incr("c") == 2
    assert await s.incr("c", amount=5) == 7


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hash():
    s = InMemoryStateStore()
    await s.hset("h", "f1", "v1")
    await s.hset("h", "f2", "v2")
    assert await s.hgetall("h") == {"f1": "v1", "f2": "v2"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_queue():
    s = InMemoryStateStore()
    await s.lpush("q", "a")
    await s.lpush("q", "b")
    assert await s.rpop("q") == "a"
    assert await s.rpop("q") == "b"
    assert await s.rpop("q") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_removes_all_types():
    s = InMemoryStateStore()
    await s.set("k", b"v")
    await s.hset("h", "f", "v")
    await s.lpush("l", "x")
    await s.delete("k")
    await s.delete("h")
    await s.delete("l")
    assert await s.get("k") is None
    assert await s.hgetall("h") == {}
    assert await s.rpop("l") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_keys_prefix():
    s = InMemoryStateStore()
    await s.set("a:1", b"x")
    await s.set("a:2", b"y")
    await s.set("b:1", b"z")
    keys = [k async for k in s.keys("a:")]
    assert sorted(keys) == ["a:1", "a:2"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_singleton():
    s = get_state_store()
    assert isinstance(s, InMemoryStateStore)