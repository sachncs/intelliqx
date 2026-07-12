"""Tests for aqip-compute."""

import asyncio

import pytest
from aqip_compute.runtime import (
    InProcessComputeRuntime,
    InvocationRequest,
    get_compute_runtime,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invoke_unknown_agent():
    rt = InProcessComputeRuntime()
    req = InvocationRequest(agent_name="nope", input={}, tenant_id="t1")
    resp = await rt.invoke(req)
    assert resp.status == "not_found"
    assert "nope" in (resp.error or "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_register_and_invoke():
    rt = InProcessComputeRuntime()

    async def handler(req: InvocationRequest) -> dict:
        return {"echo": req.input}

    rt.register("echo", handler)
    req = InvocationRequest(agent_name="echo", input={"x": 1}, tenant_id="t1")
    resp = await rt.invoke(req)
    assert resp.status == "ok"
    assert resp.output == {"echo": {"x": 1}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invoke_exception():
    rt = InProcessComputeRuntime()

    async def handler(req: InvocationRequest) -> dict:
        raise RuntimeError("boom")

    rt.register("bad", handler)
    req = InvocationRequest(agent_name="bad", input={}, tenant_id="t1")
    resp = await rt.invoke(req)
    assert resp.status == "error"
    assert "boom" in (resp.error or "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invoke_timeout():
    rt = InProcessComputeRuntime()

    async def handler(req: InvocationRequest) -> dict:
        await asyncio.sleep(1.0)
        return {}

    rt.register("slow", handler)
    req = InvocationRequest(agent_name="slow", input={}, tenant_id="t1", timeout_seconds=0)
    resp = await rt.invoke(req)
    assert resp.status == "timeout"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_duration_recorded():
    rt = InProcessComputeRuntime()

    async def handler(req: InvocationRequest) -> dict:
        await asyncio.sleep(0.05)
        return {}

    rt.register("x", handler)
    req = InvocationRequest(agent_name="x", input={}, tenant_id="t1")
    resp = await rt.invoke(req)
    assert resp.duration_ms >= 30


@pytest.mark.unit
def test_singleton():
    rt = get_compute_runtime()
    assert isinstance(rt, InProcessComputeRuntime)