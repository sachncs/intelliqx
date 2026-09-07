"""Agent registry.

A process-wide directory from ``name`` to factory. Factories (not
instances) are stored so each invocation gets a fresh agent, which
keeps agents stateless and easy to reason about.

Use :func:`register_agent` to add an agent; :func:`get_agent_registry`
to read the singleton; :func:`reset_agent_registry` between tests
for isolation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from intelliqx_agents.base import AgentMeta

__all__ = ["AgentRegistry", "get_agent_registry", "register_agent", "reset_agent_registry"]

FactoryT = TypeVar("FactoryT", bound=Callable[[], Any])


class AgentRegistry:
    """Registry of agent factories.

    Methods are deliberately thin: registration and lookup only.
    The registry does not own the agents' lifecycle (that's the
    compute runtime's job); it just maps names to constructors.
    """

    __slots__ = ("factories", "meta")

    def __init__(self) -> None:
        self.factories: dict[str, Callable[[], Any]] = {}
        self.meta: dict[str, Any] = {}

    def register(self, name: str, factory: FactoryT, *, meta: AgentMeta | None = None) -> None:
        """Register ``factory`` for ``name``.

        Args:
            name: The agent's registry key.
            factory: A zero-arg callable that returns a new agent
                instance (any Pydantic AI agent or AgentBase).
            meta: Optional :class:`AgentMeta` attached to the
                registration for later inspection.
        """
        self.factories[name] = factory
        self.meta[name] = meta

    def create(self, name: str) -> Any:
        """Construct a fresh agent instance for ``name``."""
        if name not in self.factories:
            raise KeyError(f"Agent not registered: {name!r}")
        return self.factories[name]()

    def list(self) -> list[str]:
        """Return every registered name, sorted alphabetically."""
        return sorted(self.factories.keys())

    def get_meta(self, name: str) -> Any:
        """Return the metadata attached to ``name``, or ``None``."""
        return self.meta.get(name)


SINGLETON: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """Return the singleton :class:`AgentRegistry`."""
    global SINGLETON
    if SINGLETON is None:
        SINGLETON = AgentRegistry()
    return SINGLETON


def register_agent(name: str, factory: Callable[[], Any], *, meta: AgentMeta | None = None) -> None:
    """Register ``factory`` for ``name`` in the singleton registry."""
    get_agent_registry().register(name, factory, meta=meta)


def reset_agent_registry() -> None:
    """Clear the singleton registry (for tests)."""
    global SINGLETON
    SINGLETON = None
