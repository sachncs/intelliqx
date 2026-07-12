"""Tests for intelliqx-tools."""


import pytest
from intelliqx_tools.manager import ToolManager
from intelliqx_tools.rate_limit import RateLimiter
from intelliqx_tools.registry import ToolDefinition, ToolRegistry


@pytest.mark.unit
@pytest.mark.asyncio
async def test_register_and_invoke():
    m = ToolManager()

    async def handler(payload):
        return {"echo": payload}

    m.register_tool(
        ToolDefinition(name="echo", description="echoes", rate_limit_per_minute=600),
        handler,
    )
    res = await m.invoke("echo", payload={"x": 1})
    assert res.status == "ok"
    assert res.output == {"echo": {"x": 1}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invoke_unknown_tool():
    m = ToolManager()
    res = await m.invoke("missing")
    assert res.status == "not_found"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invoke_handler_error():
    m = ToolManager()

    async def handler(payload):
        raise RuntimeError("nope")

    m.register_tool(ToolDefinition(name="bad"), handler)
    res = await m.invoke("bad")
    assert res.status == "error"
    assert "nope" in (res.error or "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limiter_throttles(monkeypatch):
    rl = RateLimiter()
    # Very low rate so we can prove throttling.
    times: list[float] = []
    for _ in range(5):
        import time

        t0 = time.monotonic()
        await rl.acquire("x", rate_per_minute=30)  # ~0.5/sec
        times.append(time.monotonic() - t0)
    # Some calls should have non-trivial delay as bucket drains.
    assert max(times) >= 0.05


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_registry_find_by_capability():
    r = ToolRegistry()
    r.register(ToolDefinition(name="github", capabilities=["vcs"]))
    r.register(ToolDefinition(name="jira", capabilities=["ticketing"]))
    r.register(ToolDefinition(name="gh_enterprise", capabilities=["vcs", "enterprise"]))
    matches = r.find_by_capability("vcs")
    assert {t.name for t in matches} == {"github", "gh_enterprise"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_registry_get_missing():
    r = ToolRegistry()
    with pytest.raises(KeyError):
        r.get("missing")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limiter_wrap(monkeypatch):
    rl = RateLimiter()
    called = []

    async def fn(x):
        called.append(x)
        return x * 2

    res = await rl.wrap("k", 600, fn, 3)
    assert res == 6
    assert called == [3]