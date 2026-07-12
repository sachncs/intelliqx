"""Agent decorators.

The framework ships one decorator, :func:`traced_agent`, which wraps
an agent's ``run`` method in an OpenTelemetry span. The decorator is
applied at class-definition time and survives pickling/serialisation,
so agents remain fully wireable.
"""

from __future__ import annotations

import functools
from collections.abc import Callable

from aqip_observability.tracing import get_tracer


def traced_agent(name: str | None = None) -> Callable:
    """Wrap an agent's ``run`` method in a tracer span.

    The span name defaults to the function's ``__qualname__`` (e.g.
    ``"PlannerAgent.run"``); pass ``name=...`` to override. The
    ``tenant_id`` and ``run_id`` are added as span attributes so
    traces can be filtered by tenant in the OTel backend.

    Example:
        >>> class FooAgent(AgentBase):
        ...     @traced_agent("foo")
        ...     async def run(self, ctx, input):
        ...         ...
    """
    def decorator(fn: Callable) -> Callable:
        agent_name = name or fn.__qualname__

        @functools.wraps(fn)
        async def wrapper(self, ctx, input):  # type: ignore[no-untyped-def]
            tracer = get_tracer()
            with tracer.span(f"agent.{agent_name}.run") as span:
                span.set_attribute("tenant_id", ctx.tenant.tenant_id)
                span.set_attribute("run_id", ctx.run_id)
                return await fn(self, ctx, input)

        return wrapper

    return decorator
