"""Compute runtime interface and in-process implementation.

The :class:`ComputeRuntime` is the contract every adapter fulfils. The
:class:`InProcessComputeRuntime` is the reference implementation used
in tests and local dev — it calls registered handlers directly,
captures exceptions as ``InvocationResponse(status="error", ...)``,
and enforces a per-call timeout via :func:`asyncio.wait_for`.

Status values:

* ``"ok"``        — handler returned within the timeout.
* ``"timeout"``   — ``asyncio.wait_for`` fired.
* ``"error"``     — handler raised any other exception.
* ``"not_found"`` — no handler was registered for the agent name.
"""

from __future__ import annotations

import abc
import asyncio
import time
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from intelliqx_observability.tracing import get_tracer
from pydantic import BaseModel, ConfigDict, Field


class InvocationRequest(BaseModel):
    """An agent invocation.

    Attributes:
        agent_name: Registry key for the agent to invoke. Used as
            the Lambda function name (``intelliqx-{agent_name}``) in AWS
            and as the URL path component on GCP.
        input: JSON-serialisable dict of agent input.
        tenant_id: Tenant scope; flows into :class:`AgentContext`.
        timeout_seconds: Per-call timeout. Enforced by
            ``asyncio.wait_for`` in the in-process runtime; the
            cloud adapters rely on the platform's native timeout.
        metadata: Free-form per-call metadata (run id, plan id, etc.).
    """

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    input: dict[str, Any]
    tenant_id: str
    timeout_seconds: int = 300
    metadata: dict[str, Any] = Field(default_factory=dict)


class InvocationResponse(BaseModel):
    """The result of an agent invocation.

    Attributes:
        agent_name: The agent that was invoked (echoed for log
            correlation).
        output: The agent's serialised output.
        duration_ms: Wall-clock duration of the invocation.
        status: One of ``"ok"``, ``"timeout"``, ``"error"``,
            ``"not_found"``.
        error: Human-readable error message (when ``status != "ok"``).
    """

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    output: dict[str, Any]
    duration_ms: int
    status: str = "ok"
    error: str | None = None


AgentCallable = Callable[[InvocationRequest], Awaitable[dict[str, Any]]]


class ComputeRuntime(abc.ABC):
    """Abstract compute runtime.

    The default implementations of both methods raise
    :class:`NotImplementedError`; subclasses must override.
    """

    @abc.abstractmethod
    async def invoke(self, request: InvocationRequest) -> InvocationResponse:
        """Invoke the agent named in ``request``.

        Args:
            request: The invocation descriptor.

        Returns:
            The :class:`InvocationResponse`. The response's status
            field is the contract; callers should not raise on
            non-``"ok"`` values.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def register(self, agent_name: str, handler: AgentCallable) -> None:
        """Register a handler for an agent.

        Args:
            agent_name: The agent's registry key.
            handler: An async callable ``(InvocationRequest) -> dict``.
        """
        raise NotImplementedError


class InProcessComputeRuntime(ComputeRuntime):
    """Run agents in-process. Used for local dev and tests.

    Handlers run in the same event loop as the caller. The runtime
    captures every exception as a structured response (it never
    raises out of ``invoke``) so the orchestrator can branch on
    ``status`` instead of try/except.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, AgentCallable] = {}

    def register(self, agent_name: str, handler: AgentCallable) -> None:
        """Register ``handler`` as the implementation of ``agent_name``."""
        self._handlers[agent_name] = handler

    async def invoke(self, request: InvocationRequest) -> InvocationResponse:
        # Wrap the whole call in a tracer span so every agent
        # invocation shows up in the OTel trace.
        tracer = get_tracer()
        with tracer.span(f"agent.{request.agent_name}.invoke") as span:
            span.set_attribute("tenant_id", request.tenant_id)
            span.set_attribute("agent_name", request.agent_name)
            handler = self._handlers.get(request.agent_name)
            if handler is None:
                return InvocationResponse(
                    agent_name=request.agent_name,
                    output={},
                    duration_ms=0,
                    status="not_found",
                    error=f"No handler registered for agent {request.agent_name!r}",
                )
            start = time.monotonic()
            try:
                output = await asyncio.wait_for(handler(request), timeout=request.timeout_seconds)
            except TimeoutError:
                duration_ms = int((time.monotonic() - start) * 1000)
                span.set_attribute("error", "timeout")
                return InvocationResponse(
                    agent_name=request.agent_name,
                    output={},
                    duration_ms=duration_ms,
                    status="timeout",
                    error="Invocation timed out",
                )
            except Exception as e:
                duration_ms = int((time.monotonic() - start) * 1000)
                span.set_attribute("error", "exception")
                return InvocationResponse(
                    agent_name=request.agent_name,
                    output={},
                    duration_ms=duration_ms,
                    status="error",
                    error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                )
            duration_ms = int((time.monotonic() - start) * 1000)
            span.set_attribute("duration_ms", duration_ms)
            return InvocationResponse(
                agent_name=request.agent_name,
                output=output,
                duration_ms=duration_ms,
                status="ok",
            )


_SINGLETON: ComputeRuntime | None = None


def get_compute_runtime() -> ComputeRuntime:
    """Return the singleton compute runtime.

    Defaults to :class:`InProcessComputeRuntime`. Production
    deployments should construct a cloud adapter once at startup
    and call :func:`set_compute_runtime` to install it.
    """
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = InProcessComputeRuntime()
    return _SINGLETON


def set_compute_runtime(runtime: ComputeRuntime) -> None:
    """Replace the singleton compute runtime.

    Used by application bootstrap to install a configured cloud
    adapter before the first :func:`get_compute_runtime` call.
    """
    global _SINGLETON
    _SINGLETON = runtime


def reset_compute_runtime() -> None:
    """Clear the singleton compute runtime (for tests)."""
    global _SINGLETON
    _SINGLETON = None
