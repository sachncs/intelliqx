"""Agent decorators.

Currently exposes :func:`traced_agent`, the canonical way to wrap
an :meth:`AgentBase.run` implementation in an OpenTelemetry span
tagged with tenant + run ids.
"""

from __future__ import annotations

import functools
from collections.abc import Callable

from intelliqx_observability.tracing import get_tracer


def traced_agent(name: str | None = None) -> Callable:
    """Wrap an agent's ``run`` method in a tracer span.

    Apply the decorator to the ``run`` method on a concrete
    :class:`~intelliqx_agents.base.AgentBase` subclass::

        class PlannerAgent(AgentBase):
            @traced_agent("planner")
            async def run(self, ctx, input):
                ...

    The wrapper opens a span named ``"agent.<name>.run"`` and tags
    it with ``tenant_id`` and ``run_id`` attributes drawn from the
    :class:`~intelliqx_agents.base.AgentContext`. Nested spans
    (LLM calls, sub-agents) inherit the trace context.

    Args:
        name: Override the agent name embedded in the span name.
            Defaults to ``fn.__qualname__``.

    Returns:
        A decorator that wraps the target async ``run`` method.
    """

    def decorator(fn: Callable) -> Callable:
        agent_name = name or fn.__qualname__

        @functools.wraps(fn)
        async def wrapper(self: object, ctx: object, input: object) -> object:
            tracer = get_tracer()
            # ``agent.<name>.run`` mirrors the convention used by
            # compute-runtime spans (``agent.<name>.invoke``) so
            # backends group them under the same prefix.
            with tracer.span(f"agent.{agent_name}.run") as span:
                span.set_attribute("tenant_id", ctx.tenant.tenant_id)  # type: ignore[attr-defined]
                span.set_attribute("run_id", ctx.run_id)  # type: ignore[attr-defined]
                return await fn(self, ctx, input)

        return wrapper

    return decorator
