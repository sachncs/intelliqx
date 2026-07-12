"""Agent decorators."""

from __future__ import annotations

import functools
from collections.abc import Callable

from intelliqx_observability.tracing import get_tracer


def traced_agent(name: str | None = None) -> Callable:
    """Decorator: wrap an agent's run method in a tracer span."""

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