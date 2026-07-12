"""Tool manager — MCP-compatible tool gateway.

AQIP agents call external systems (GitHub, Jira, Slack, PagerDuty,
sandboxed shell) through a single interface
(:class:`aqip_tools.manager.ToolManager`). The manager handles:

* **Discovery** via :class:`ToolRegistry` (name + capabilities + rate
  limits).
* **Routing** to a registered async handler.
* **Rate limiting** via a per-tool token bucket (see
  :class:`aqip_tools.rate_limit.RateLimiter`).
* **Failure isolation** — exceptions in a handler are caught and
  returned as a structured :class:`ToolInvocationResult` with
  ``status="error"``; the agent's main flow keeps running.

The shape is intentionally compatible with the Model Context Protocol
(MCP) tool interface, so a future migration to MCP is mechanical.
"""

from aqip_tools.manager import ToolInvocationResult, ToolManager, get_tool_manager
from aqip_tools.rate_limit import RateLimiter
from aqip_tools.registry import ToolDefinition, ToolRegistry

__all__ = [
    "RateLimiter",
    "ToolDefinition",
    "ToolInvocationResult",
    "ToolManager",
    "ToolRegistry",
    "get_tool_manager",
]
