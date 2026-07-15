"""Tool execution manager.

A :class:`ToolManager` owns a :class:`ToolRegistry` (the catalog of
known tools) and a private handler map (the callables that
implement each tool). Every call to :meth:`invoke` goes through:

1. **Discovery check.** If the tool is not in the handler map, the
   manager returns a ``not_found`` result — no exception.
2. **Rate-limit acquire.** The per-tool token bucket is consulted;
   ``acquire`` blocks (cooperatively, via ``asyncio.sleep``) until a
   token is available.
3. **Handler call.** The async handler is awaited. Any exception is
   converted to a structured ``error`` result.
4. **Result packaging.** The output is wrapped in
   :class:`ToolInvocationResult` with a status string the agent can
   branch on.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from intelliqx_tools.rate_limit import RateLimiter
from intelliqx_tools.registry import ToolDefinition, ToolRegistry


class ToolInvocationResult(BaseModel):
    """The result of a tool invocation.

    Attributes:
        tool: The tool name.
        status: ``"ok"``, ``"not_found"``, or ``"error"``.
        output: Tool-specific output (any JSON-serialisable value).
        error: Human-readable error message on failure.
    """

    model_config = ConfigDict(extra="forbid")

    tool: str
    status: str
    output: Any = None
    error: str | None = None


ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


class ToolManager:
    """Tool execution manager.

    Args:
        registry: Optional pre-built :class:`ToolRegistry`. A new
            one is created on demand if omitted.
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or ToolRegistry()
        # tool name -> handler callable
        self.handlers: dict[str, ToolHandler] = {}
        self.rate_limiter = RateLimiter()

    def register_tool(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        """Register a tool definition and its handler.

        Args:
            definition: The tool's metadata.
            handler: The async callable that implements the tool.
                Signature: ``(payload: dict) -> Any``.
        """
        self.registry.register(definition)
        self.handlers[definition.name] = handler

    async def invoke(
        self, name: str, *, payload: dict[str, Any] | None = None
    ) -> ToolInvocationResult:
        """Invoke a registered tool.

        Args:
            name: The tool name (must be in the handler map).
            payload: Tool-specific payload. Defaults to ``{}``.

        Returns:
            A :class:`ToolInvocationResult` whose ``status`` field
            is one of ``"ok"``, ``"not_found"``, or ``"error"``.
            Exceptions are caught and surfaced as ``status="error"``;
            the agent's main flow is never interrupted by a tool
            crash.
        """
        if name not in self.handlers:
            return ToolInvocationResult(
                tool=name, status="not_found", error=f"No handler for {name!r}"
            )
        definition = self.registry.get(name)
        # The rate limiter blocks cooperatively until a token is
        # available; this is the only place the call may pause.
        await self.rate_limiter.acquire(name, definition.rate_limit_per_minute)
        try:
            output = await self.handlers[name](payload or {})
            return ToolInvocationResult(tool=name, status="ok", output=output)
        except Exception as e:
            return ToolInvocationResult(tool=name, status="error", error=f"{type(e).__name__}: {e}")


SINGLETON: ToolManager | None = None


def get_tool_manager() -> ToolManager:
    """Return the singleton :class:`ToolManager`.

    Use :func:`reset_tool_manager` between tests for isolation.
    """
    global SINGLETON
    if SINGLETON is None:
        SINGLETON = ToolManager()
    return SINGLETON


def set_tool_manager(mgr: ToolManager) -> None:
    """Replace the singleton tool manager."""
    global SINGLETON
    SINGLETON = mgr


def reset_tool_manager() -> None:
    """Clear the singleton tool manager (for tests)."""
    global SINGLETON
    SINGLETON = None
