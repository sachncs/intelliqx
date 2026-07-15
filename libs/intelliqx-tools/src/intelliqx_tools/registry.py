"""Tool definition and in-process registry.

The :class:`ToolRegistry` is a thin dictionary wrapper. The interesting
parts of the tool model live on :class:`ToolDefinition` itself:
``capabilities`` (for discovery), ``rate_limit_per_minute`` (for
throttling), and the optional ``input_schema`` / ``output_schema``
(for marketplace validation).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ToolDefinition", "ToolRegistry"]


class ToolDefinition(BaseModel):
    """Definition of an external tool.

    Attributes:
        name: Unique tool name. By convention ``"<service>.<action>"``
            (e.g. ``"github.issue"``, ``"slack.message"``).
        version: SemVer string. Marketplace agents may pin to a
            specific version.
        description: One-line human-readable description.
        input_schema: Optional JSON Schema for the tool's input.
        output_schema: Optional JSON Schema for the tool's output.
        rate_limit_per_minute: Per-tool throttle. Default 60.
        capabilities: Tags for discovery (``["vcs"]``, ``["ticketing"]``).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str = "1.0.0"
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    rate_limit_per_minute: int = 60
    capabilities: list[str] = Field(default_factory=list)


class ToolRegistry:
    """In-process tool registry.

    A simple dict wrapper; intentionally not thread-safe (the
    registry is mutated only at startup, never on the hot path).
    """

    def __init__(self) -> None:
        self.tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register or replace ``tool``."""
        self.tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        """Return the definition for ``name``.

        Raises:
            KeyError: If the tool is not registered.
        """
        if name not in self.tools:
            raise KeyError(f"Tool not found: {name!r}")
        return self.tools[name]

    def list_tools(self) -> list[ToolDefinition]:
        """Return every registered definition."""
        return list(self.tools.values())

    def find_by_capability(self, capability: str) -> list[ToolDefinition]:
        """Return every tool tagged with ``capability``.

        Linear scan; fine for the few hundred tools the platform
        expects to support.
        """
        return [t for t in self.tools.values() if capability in t.capabilities]
