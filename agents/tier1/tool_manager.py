"""Tool Manager Agent (Tier 1).

Provides a tool invocation gateway. Registers and routes to
MCP-compatible tools via :class:`intelliqx_tools.manager.ToolManager`.
Ships with five starter tools used by tests and the default dev
profile: GitHub issue creation, Jira ticket creation, Slack
message posting, PagerDuty alert, and a sandboxed local shell.
"""

from __future__ import annotations

from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_tools.manager import ToolManager, get_tool_manager
from intelliqx_tools.registry import ToolDefinition
from pydantic import BaseModel, ConfigDict, Field


class ToolInvoke(BaseModel):
    """A tool invocation request.

    Attributes:
        tool: The tool name (e.g. ``"github.issue"``).
        payload: Tool-specific input. Schema is enforced by the
            tool's registered :class:`ToolDefinition`.
    """

    model_config = ConfigDict(extra="forbid")

    tool: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolOutput(BaseModel):
    """The result of a tool invocation.

    Attributes:
        tool: Echoed tool name.
        status: One of ``"ok"``, ``"not_found"``, ``"error"``
            (returned by :class:`intelliqx_tools.manager.ToolManager`).
        output: Tool-specific output.
        error: Error message on failure.
    """

    model_config = ConfigDict(extra="forbid")

    tool: str
    status: str
    output: Any = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Starter tool implementations (mocks)
# ---------------------------------------------------------------------------
#
# These handlers are pure simulations — they never reach the network.
# Production deployments register real handlers that talk to GitHub,
# Jira, etc.


async def _github_issue(payload: dict[str, Any]) -> dict[str, Any]:
    """Mock GitHub issue creation."""
    return {
        "issue_number": payload.get("issue_number", 1),
        "url": f"https://github.example.com/org/repo/issues/{payload.get('issue_number', 1)}",
        "title": payload.get("title", ""),
        "state": "open",
    }


async def _jira_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    """Mock Jira ticket creation."""
    return {
        "key": payload.get("key", "QA-1"),
        "status": "To Do",
        "summary": payload.get("summary", ""),
    }


async def _slack_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Mock Slack message post."""
    return {
        "channel": payload.get("channel", "#general"),
        "ts": "1700000000.000100",
        "text": payload.get("text", ""),
    }


async def _pagerduty_alert(payload: dict[str, Any]) -> dict[str, Any]:
    """Mock PagerDuty alert trigger."""
    return {
        "incident_key": payload.get("incident_key", "INC-1"),
        "status": "triggered",
        "service": payload.get("service", "intelliqx"),
    }


async def _local_shell(payload: dict[str, Any]) -> dict[str, Any]:
    """Sandboxed local shell (echo / ls / cat / pwd / whoami only).

    Commands outside the whitelist are rejected with exit 126.
    The handler never actually executes anything — it returns a
    ``[simulated:<cmd>]`` string for the allowed commands so tests
    can assert the call was made.
    """
    allowed = {"echo", "ls", "cat", "pwd", "whoami"}
    cmd = payload.get("cmd", "")
    parts = cmd.split()
    if not parts or parts[0] not in allowed:
        return {
            "stdout": "",
            "stderr": f"command not allowed: {parts[0] if parts else ''}",
            "exit": 126,
        }
    # Pure simulation — never actually executes.
    return {"stdout": f"[simulated:{parts[0]}]", "stderr": "", "exit": 0}


def default_tool_manager() -> ToolManager:
    """Return a :class:`ToolManager` pre-loaded with the five starter tools.

    Idempotent: calling more than once returns the same singleton
    with the same registrations.
    """
    mgr = get_tool_manager()
    if not mgr.registry.list():
        mgr.register_tool(
            ToolDefinition(
                name="github.issue",
                description="Create a GitHub issue.",
                capabilities=["vcs", "issue_tracking"],
                rate_limit_per_minute=60,
            ),
            _github_issue,
        )
        mgr.register_tool(
            ToolDefinition(
                name="jira.ticket",
                description="Create a Jira ticket.",
                capabilities=["ticketing"],
                rate_limit_per_minute=60,
            ),
            _jira_ticket,
        )
        mgr.register_tool(
            ToolDefinition(
                name="slack.message",
                description="Post a Slack message.",
                capabilities=["messaging"],
                rate_limit_per_minute=120,
            ),
            _slack_message,
        )
        mgr.register_tool(
            ToolDefinition(
                name="pagerduty.alert",
                description="Trigger a PagerDuty alert.",
                capabilities=["alerting"],
                rate_limit_per_minute=30,
            ),
            _pagerduty_alert,
        )
        mgr.register_tool(
            ToolDefinition(
                name="local_shell",
                description="Sandboxed local shell (echo/ls/cat/pwd/whoami only).",
                capabilities=["shell"],
                rate_limit_per_minute=300,
            ),
            _local_shell,
        )
    return mgr


class ToolManagerAgent(AgentBase):
    """Routes tool invocations through the configured :class:`ToolManager`."""

    META = AgentMeta(
        name="tool_manager",
        tier=1,
        version="0.1.0",
        description="Universal tool gateway (MCP-compatible).",
    )
    INPUT_MODEL = ToolInvoke
    OUTPUT_MODEL = ToolOutput

    @traced_agent("tool_manager")
    async def run(self, ctx: AgentContext, input: ToolInvoke) -> ToolOutput:
        mgr = default_tool_manager()
        res = await mgr.invoke(input.tool, payload=input.payload)
        return ToolOutput(tool=res.tool, status=res.status, output=res.output, error=res.error)
