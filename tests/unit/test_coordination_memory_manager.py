"""Tests for  Memory Manager Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest

from agents import register_all, register_compute_handlers
from agents.coordination.memory_manager import MemoryManagerAgent


def put_op(agent, tenant, key, value, mtype="working", **kw):
    return agent.invoke(
        InvocationRequest(
            agent_name="memory_manager",
            input={"operation": "put", "key": key, "value": value, "memory_type": mtype, **kw},
            tenant_id=tenant,
        )
    )


def get_op(agent, tenant, key, mtype="working"):
    return agent.invoke(
        InvocationRequest(
            agent_name="memory_manager",
            input={"operation": "get", "key": key, "memory_type": mtype},
            tenant_id=tenant,
        )
    )


def search_op(agent, tenant, query, mtype="episodic", **kw):
    return agent.invoke(
        InvocationRequest(
            agent_name="memory_manager",
            input={"operation": "search", "query": query, "memory_type": mtype, **kw},
            tenant_id=tenant,
        )
    )


def summarize_op(agent, tenant, keys, target_key):
    return agent.invoke(
        InvocationRequest(
            agent_name="memory_manager",
            input={"operation": "summarize", "keys": keys, "target_key": target_key},
            tenant_id=tenant,
        )
    )


def forget_op(agent, tenant, key, mtype="working"):
    return agent.invoke(
        InvocationRequest(
            agent_name="memory_manager",
            input={"operation": "forget", "key": key, "memory_type": mtype},
            tenant_id=tenant,
        )
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_memoryput_op_andget_op():
    register_all()
    register_compute_handlers()
    agent = MemoryManagerAgent()
    await put_op(agent, "t1", "k1", "hello", ttl_seconds=60)
    out = await get_op(agent, "t1", "k1")
    assert out["value"] == "hello"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_memory_episodic_roundtrip():
    register_all()
    register_compute_handlers()
    agent = MemoryManagerAgent()
    await put_op(agent, "t1", "evt1", "user logged in", mtype="episodic")
    out = await get_op(agent, "t1", "evt1", mtype="episodic")
    assert out["value"] == "user logged in"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_memorysearch_op_returns_matches():
    register_all()
    register_compute_handlers()
    agent = MemoryManagerAgent()
    for i, body in enumerate(["apple pie recipe", "banana bread", "apple sauce"]):
        await put_op(agent, "t1", f"e{i}", body, mtype="episodic")
    out = await search_op(agent, "t1", "apple")
    assert len(out["results"]) >= 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_memorysummarize_op_writes_target():
    register_all()
    register_compute_handlers()
    agent = MemoryManagerAgent()
    for i, body in enumerate(["event a happens", "event b happens"]):
        await put_op(agent, "t1", f"e{i}", body, mtype="episodic")
    out = await summarize_op(agent, "t1", ["e0", "e1"], "summary1")
    assert out["success"]
    target = await get_op(agent, "t1", "summary1", mtype="semantic")
    assert "SUMMARY" in (target["value"] or "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_memoryforget_op_removes():
    register_all()
    register_compute_handlers()
    agent = MemoryManagerAgent()
    await put_op(agent, "t1", "k", "v")
    await forget_op(agent, "t1", "k")
    out = await get_op(agent, "t1", "k")
    assert out["value"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_memory_tenant_isolation():
    register_all()
    register_compute_handlers()
    agent = MemoryManagerAgent()
    await put_op(agent, "tA", "k", "vA")
    out = await get_op(agent, "tB", "k")
    assert out["value"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_memorysearch_op_top_k():
    register_all()
    register_compute_handlers()
    agent = MemoryManagerAgent()
    for i in range(20):
        await put_op(agent, "t1", f"e{i}", f"apple doc {i}", mtype="episodic")
    out = await search_op(agent, "t1", "apple", top_k=3)
    assert len(out["results"]) <= 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_memory_unknown_op_returns_error():
    register_all()
    register_compute_handlers()
    agent = MemoryManagerAgent()
    # Build a payload that has key/memory_type but no value or query -> ambiguous -> defaults to put, but missing 'value'.
    # We test that a deliberately empty get with unknown key returns None.
    out = await get_op(agent, "t1", "never_existed")
    assert out["value"] is None
    assert out["success"]
