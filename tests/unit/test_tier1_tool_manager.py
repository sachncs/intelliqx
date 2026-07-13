"""Tests for Tier 1 Tool Manager Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest

from agents import register_all, register_compute_handlers
from agents.coordination.tool_manager import ToolManagerAgent, default_tool_manager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_manager_github():
    register_all()
    register_compute_handlers()
    mgr = default_tool_manager()
    assert any(t.name == "github.issue" for t in mgr.registry.list_tools())

    agent = ToolManagerAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="tool_manager",
            input={"tool": "github.issue", "payload": {"title": "bug", "issue_number": 42}},
            tenant_id="t1",
        )
    )
    assert out["status"] == "ok"
    assert out["output"]["issue_number"] == 42


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_manager_jira():
    register_all()
    register_compute_handlers()
    agent = ToolManagerAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="tool_manager",
            input={"tool": "jira.ticket", "payload": {"key": "QA-9", "summary": "test"}},
            tenant_id="t1",
        )
    )
    assert out["status"] == "ok"
    assert out["output"]["key"] == "QA-9"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_manager_slack():
    register_all()
    register_compute_handlers()
    agent = ToolManagerAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="tool_manager",
            input={"tool": "slack.message", "payload": {"channel": "#qa", "text": "hi"}},
            tenant_id="t1",
        )
    )
    assert out["status"] == "ok"
    assert out["output"]["channel"] == "#qa"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_manager_pagerduty():
    register_all()
    register_compute_handlers()
    agent = ToolManagerAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="tool_manager",
            input={"tool": "pagerduty.alert", "payload": {"service": "x"}},
            tenant_id="t1",
        )
    )
    assert out["status"] == "ok"
    assert out["output"]["status"] == "triggered"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_manager_local_shell_allowed():
    register_all()
    register_compute_handlers()
    agent = ToolManagerAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="tool_manager",
            input={"tool": "local_shell", "payload": {"cmd": "echo hello"}},
            tenant_id="t1",
        )
    )
    assert out["status"] == "ok"
    assert "echo" in out["output"]["stdout"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_manager_local_shell_rejected():
    register_all()
    register_compute_handlers()
    agent = ToolManagerAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="tool_manager",
            input={"tool": "local_shell", "payload": {"cmd": "rm -rf /"}},
            tenant_id="t1",
        )
    )
    assert out["status"] == "ok"  # handler returns 'not allowed' as output, not error
    assert out["output"]["exit"] == 126


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_manager_unknown_tool():
    register_all()
    register_compute_handlers()
    agent = ToolManagerAgent()
    out = await agent.invoke(
        InvocationRequest(agent_name="tool_manager", input={"tool": "missing"}, tenant_id="t1")
    )
    assert out["status"] == "not_found"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_manager_rate_limit(monkeypatch):
    register_all()
    register_compute_handlers()
    agent = ToolManagerAgent()
    # Force a low rate limit on the slack tool
    from intelliqx_tools.manager import get_tool_manager

    mgr = get_tool_manager()
    for t in mgr.registry.list_tools():
        if t.name == "slack.message":
            t.rate_limit_per_minute = 1
    # First call OK; subsequent calls should be throttled but eventually succeed.
    results = []
    for _ in range(3):
        out = await agent.invoke(
            InvocationRequest(
                agent_name="tool_manager",
                input={"tool": "slack.message", "payload": {"text": "x"}},
                tenant_id="t1",
            )
        )
        results.append(out["status"])
    assert "ok" in results
