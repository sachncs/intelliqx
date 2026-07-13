"""Agent registry.

A process-wide directory from ``name`` to factory. Factories (not
instances) are stored so each invocation gets a fresh agent, which
keeps agents stateless and easy to reason about.

Use :func:`register_agent` to add an agent; :func:`get_agent_registry`
to read the singleton; :func:`reset_agent_registry` between tests
for isolation.
"""

from __future__ import annotations

from typing import Any

from intelliqx_agents.base import AgentBase, AgentFactory


class AgentRegistry:
    """Registry of agent factories.

    Methods are deliberately thin: registration and lookup only.
    The registry does not own the agents' lifecycle (that's the
    compute runtime's job); it just maps names to constructors.
    """

    def __init__(self) -> None:
        self.__factories: dict[str, AgentFactory] = {}
        self.__meta: dict[str, Any] = {}

    def register(self, name: str, factory: AgentFactory, *, meta: Any | None = None) -> None:
        """Register a factory for ``name``.

        Args:
            name: The agent's registry key.
            factory: A zero-arg callable that returns a new
                :class:`AgentBase` instance.
            meta: Optional :class:`intelliqx_agents.base.AgentMeta` (or
                anything else) attached to the registration for
                later inspection.
        """
        self.__factories[name] = factory
        self.__meta[name] = meta

    def create(self, name: str) -> AgentBase:
        """Construct a fresh agent instance for ``name``.

        Raises:
            KeyError: If no factory is registered for ``name``.
        """
        if name not in self.__factories:
            raise KeyError(f"Agent not registered: {name!r}")
        return self.__factories[name]()

    def list(self) -> list[str]:
        """Return every registered name, sorted alphabetically."""
        return sorted(self.__factories.keys())

    def get_meta(self, name: str) -> Any:
        """Return the metadata attached to ``name``, or ``None``."""
        return self.__meta.get(name)


_SINGLETON: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """Return the singleton :class:`AgentRegistry`."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = AgentRegistry()
    return _SINGLETON


def register_agent(name: str, factory: AgentFactory, *, meta: Any | None = None) -> None:
    """Register ``factory`` for ``name`` in the singleton registry."""
    get_agent_registry().register(name, factory, meta=meta)


def reset_agent_registry() -> None:
    """Clear the singleton registry (for tests)."""
    global _SINGLETON
    _SINGLETON = None
