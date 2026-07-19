"""IntelliqX agent roles.

Every role is a single Pydantic AI ``Agent`` produced by the helpers
in :mod:`agents.ai._roles`. The :func:`register_all` and
:func:`register_compute_handlers` shims keep the runtime and
existing tests working while we phase out the legacy framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent

from agents.ai import _roles

__all__ = [
    "AGENT_CATALOG",
    "AgentRole",
    "build_catalog",
    "register_all",
    "register_compute_handlers",
]

AGENT_CATALOG: list[tuple[str, Any]] = []


@dataclass(frozen=True)
class AgentRole:
    """A registered agent role.

    Attributes:
        name: Unique registry key.
        category: Coordination, intelligence, execution, or
            governance.
        description: One-line summary used for marketplace listings
            and logs.
        builder: Zero-arg factory that returns a fully-configured
            Pydantic AI ``Agent``.
    """

    name: str
    category: str
    description: str
    builder: type[Agent[Any, Any]]


def build_catalog() -> list[tuple[str, Any]]:
    """Lazy catalog builder; ``register_all`` consumes the result."""
    if AGENT_CATALOG:
        return AGENT_CATALOG
    AGENT_CATALOG.extend(_roles.build())
    return AGENT_CATALOG


def register_all() -> None:
    """Register every role's class with the agent registry."""
    from intelliqx_agents.registry import get_agent_registry

    catalog = build_catalog()
    reg = get_agent_registry()
    for role in catalog:
        reg.register(role.name, role.builder, meta=_meta_from(role))


def _meta_from(role: AgentRole) -> Any:
    from intelliqx_agents.base import AgentMeta

    return AgentMeta(
        name=role.name, category=role.category, version="1.0.0", description=role.description
    )


def register_compute_handlers() -> None:
    """Register every role's ``run`` method with the in-process compute runtime.

    Each handler invokes the Pydantic AI agent synchronously with the
    request's input dict and returns the structured output as a JSON
    dict.
    """
    from intelliqx_compute.runtime import InvocationRequest, get_compute_runtime

    catalog = build_catalog()
    runtime = get_compute_runtime()
    for role in catalog:
        builder = role.builder

        async def handler(req: InvocationRequest, _builder=builder) -> dict[str, Any]:
            from intelliqx_agents.base import RunContext, bind_run

            run_id = req.metadata.get("run_id", "ad-hoc")
            plan_id = req.metadata.get("plan_id", "")
            run_ctx = RunContext(
                run_id=run_id,
                plan_id=plan_id,
                tenant_id=req.tenant_id,
                agent_name=req.agent_name,
                node_id=req.metadata.get("node_id"),
            )
            agent = _builder()
            with bind_run(run_ctx):
                output = await agent.run(req.input, deps=None, message_history=[])
            return output.output if hasattr(output, "output") else {"output": output}

        runtime.register(role.name, handler)
