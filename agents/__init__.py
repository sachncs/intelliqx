"""IntelliqX agent roles.

Every role is a single Pydantic AI :class:`Agent` produced by the
helpers in :mod:`agents.ai.roles`. The two functions exported here
(:func:`register_all` and :func:`register_compute_handlers`) wire
the catalog into the agent registry and the in-process compute
runtime.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import Agent

from agents.ai import roles

__all__ = [
    "AGENT_CATALOG",
    "AgentRole",
    "build_catalog",
    "register_all",
    "register_compute_handlers",
]

AGENT_CATALOG: list[roles.AgentRole] = []


def build_catalog() -> list[roles.AgentRole]:
    """Lazily build and cache the agent catalog."""
    if AGENT_CATALOG:
        return AGENT_CATALOG
    AGENT_CATALOG.extend(roles.build_roles())
    return AGENT_CATALOG


def register_all() -> None:
    """Register every role's factory with the singleton agent registry."""
    from intelliqx_agents.registry import get_agent_registry

    registry = get_agent_registry()
    for role in build_catalog():
        registry.register(role.name, role.factory, meta=meta_for(role))


def meta_for(role: roles.AgentRole) -> Any:
    """Build the ``AgentMeta`` for a single role from the registry table."""
    from intelliqx_agents.base import AgentMeta
    from intelliqx_core.models import AgentCategory

    try:
        category = AgentCategory(role.category)
    except ValueError as exc:
        raise ValueError(f"Role {role.name!r} has unknown category {role.category!r}") from exc
    return AgentMeta(
        name=role.name, category=category, version="1.0.0", description=role.description
    )


def register_compute_handlers() -> None:
    """Register each role's run handler with the in-process compute runtime."""
    from intelliqx_agents.base import RunContext, bind_run
    from intelliqx_compute.runtime import InvocationRequest, get_compute_runtime

    runtime = get_compute_runtime()
    for role in build_catalog():
        builder = role.factory

        async def handle(req: InvocationRequest, *, _builder=builder) -> dict[str, Any]:
            run_ctx = RunContext(
                run_id=req.metadata.get("run_id", "ad-hoc"),
                plan_id=req.metadata.get("plan_id", ""),
                tenant_id=req.tenant_id,
                agent_name=req.agent_name,
                node_id=req.metadata.get("node_id"),
            )
            agent: Agent[Any, Any] = _builder()
            with bind_run(run_ctx):
                prompt = json.dumps(req.input, sort_keys=True, default=str)
                result = await agent.run(prompt, deps=None, message_history=[])
            return _serialise_agent_output(result)

        runtime.register(role.name, handle)


def _serialise_agent_output(result: Any) -> dict[str, Any]:
    """Convert a Pydantic AI :class:`AgentRunResult` to a JSON-serialisable dict."""
    data = result.output if hasattr(result, "output") else result
    if hasattr(data, "model_dump"):
        return data.model_dump()
    if isinstance(data, str):
        return {"result": data}
    return {"result": data}
