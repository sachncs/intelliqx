"""Agent framework for AQIP.

The agent framework is the spine of the platform. It defines:

* :class:`AgentBase` — the base class every concrete agent inherits
  from. Provides the ``INPUT_MODEL`` / ``OUTPUT_MODEL`` contract,
  default ``invoke`` adapter (request → context → run), and
  pre-configured logger / metrics / tracer handles.
* :class:`AgentMeta` — the static metadata every agent declares
  (name, tier, version, description).
* :class:`AgentContext` — the runtime context propagated through
  every agent call.
* :class:`AgentRegistry` — a process-wide directory mapping agent
  names to factories. Factories (not instances) are stored so each
  invocation gets a fresh agent.
* :func:`traced_agent` — a decorator that wraps an agent's
  ``run`` method in an OTel span with ``tenant_id`` and
  ``run_id`` attributes.

The framework is intentionally **storage- and compute-agnostic**.
Agents call into :mod:`aqip_storage`, :mod:`aqip_state`,
:mod:`aqip_events`, and :mod:`aqip_compute` singletons; the same
agent code runs in any deployment.
"""

from aqip_agents.base import AgentBase, AgentContext, AgentFactory, AgentMeta
from aqip_agents.decorators import traced_agent
from aqip_agents.registry import (
    AgentRegistry,
    get_agent_registry,
    register_agent,
    reset_agent_registry,
)

__all__ = [
    "AgentBase",
    "AgentContext",
    "AgentFactory",
    "AgentMeta",
    "AgentRegistry",
    "get_agent_registry",
    "register_agent",
    "reset_agent_registry",
    "traced_agent",
]
