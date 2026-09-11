"""IntelliqX agent roles.

Every role is a single Pydantic AI :class:`Agent` produced by the
helpers in :mod:`agents.ai.roles`. The two functions exported here
(:func:`register_all` and :func:`register_compute_handlers`) wire
the catalog into the agent registry and the in-process compute
runtime.

The catalog is held inside the :func:`_catalog` cache function so
that :func:`reset_catalog` can wipe it between tests; the prior
implementation used a module-level mutable list, which leaked state
across tests when one case mutated the list.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import Agent

from agents.ai import roles

__all__ = [
    "AgentRole",
    "build_catalog",
    "register_all",
    "register_compute_handlers",
    "reset_catalog",
]

_CATALOG: list[roles.AgentRole] | None = None


def reset_catalog() -> None:
    """Drop the cached catalog so the next :func:`build_catalog` rebuilds it.

    Tests call this in their autouse fixture to keep state clean
    between cases.
    """
    global _CATALOG
    _CATALOG = None


def build_catalog() -> list[roles.AgentRole]:
    """Lazily build and cache the agent catalog."""
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = list(roles.build_roles())
    return _CATALOG


def register_all() -> None:
    """Register every role's factory with the singleton agent registry.

    Repeated calls are idempotent: re-registering the same name with
    the same factory is a no-op; re-registering a name with a
    different factory raises so callers notice the change.
    """
    from intelliqx_agents.registry import get_agent_registry

    registry = get_agent_registry()
    catalog = build_catalog()
    catalog_names = {role.name for role in catalog}
    existing = set(registry.factories)
    if not existing.issubset(catalog_names):
        raise RuntimeError(
            "register_all would drop existing registrations not in the "
            f"catalog; refusing. Unknown names: {sorted(existing - catalog_names)}"
        )
    for role in catalog:
        existing_factory = registry.factories.get(role.name)
        if existing_factory is not None and existing_factory is not role.factory:
            raise RuntimeError(
                f"register_all would replace the factory for {role.name!r} "
                "with a different callable; refusing to clobber prior state."
            )
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
