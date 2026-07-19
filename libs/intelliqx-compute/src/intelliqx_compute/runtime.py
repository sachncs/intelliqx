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

Errors are kept concise on the wire: only ``"{ExceptionType}: {msg}"``
goes into :attr:`InvocationResponse.error`. Full tracebacks are
captured once in the structured logger, with the active OTel span
correlation, so callers do not have to parse formatted tracebacks to
branch on the failure.
"""

from __future__ import annotations

import abc
import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from intelliqx_observability.logging import get_logger
from intelliqx_observability.tracing import get_tracer
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "COMPUTE_RUNTIME_REGISTRY",
    "ComputeRuntime",
    "InProcessComputeRuntime",
    "InvocationRequest",
    "InvocationResponse",
    "get_compute_runtime",
    "list_compute_runtimes",
    "register_compute_runtime",
    "reset_compute_runtime",
    "set_compute_runtime",
]

_logger = get_logger(__name__)


class InvocationRequest(BaseModel):
    """An agent invocation.

    Attributes:
        agent_name: Registry key for the agent to invoke.
        input: JSON-serialisable dict of agent input.
        tenant_id: Tenant scope; flows into :class:`AgentContext`.
        timeout_seconds: Per-call timeout. Enforced by
            ``asyncio.wait_for`` in the in-process runtime.
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
        error: Human-readable error message of the form
            ``"{ExceptionType}: {msg}"`` when ``status != "ok"``.
            Full tracebacks are not included on the wire — they are
            emitted to the structured logger under the active OTel
            span context.
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

    __slots__ = ("handlers",)

    def __init__(self) -> None:
        self.handlers: dict[str, AgentCallable] = {}

    def register(self, agent_name: str, handler: AgentCallable) -> None:
        """Register ``handler`` as the implementation of ``agent_name``."""
        self.handlers[agent_name] = handler

    async def invoke(self, request: InvocationRequest) -> InvocationResponse:
        tracer = get_tracer()
        with tracer.span(f"agent.{request.agent_name}.invoke") as span:
            span.set_attribute("tenant_id", request.tenant_id)
            span.set_attribute("agent_name", request.agent_name)
            handler = self.handlers.get(request.agent_name)
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
                span.set_status_error("timeout")
                _logger.warning(
                    "compute_invoke_timeout",
                    agent_name=request.agent_name,
                    tenant_id=request.tenant_id,
                    duration_ms=duration_ms,
                    timeout_seconds=request.timeout_seconds,
                )
                return InvocationResponse(
                    agent_name=request.agent_name,
                    output={},
                    duration_ms=duration_ms,
                    status="timeout",
                    error="Invocation timed out",
                )
            except Exception as e:
                duration_ms = int((time.monotonic() - start) * 1000)
                span.set_status_error("exception")
                _logger.exception(
                    "compute_invoke_error",
                    agent_name=request.agent_name,
                    tenant_id=request.tenant_id,
                    duration_ms=duration_ms,
                )
                return InvocationResponse(
                    agent_name=request.agent_name,
                    output={},
                    duration_ms=duration_ms,
                    status="error",
                    error=f"{type(e).__name__}: {e}",
                )
            duration_ms = int((time.monotonic() - start) * 1000)
            span.set_attribute("duration_ms", duration_ms)
            return InvocationResponse(
                agent_name=request.agent_name, output=output, duration_ms=duration_ms, status="ok"
            )


SINGLETON: ComputeRuntime | None = None


COMPUTE_RUNTIME_REGISTRY: dict[str, type[ComputeRuntime]] = {"in_process": InProcessComputeRuntime}


def register_compute_runtime(name: str, factory: type[ComputeRuntime]) -> None:
    """Register or replace a compute runtime factory.

    The factory is a zero-arg callable that returns a
    :class:`ComputeRuntime` instance (typically the adapter class
    itself). Use this to plug in a custom runtime without modifying
    the call site of :func:`get_compute_runtime`.
    """
    COMPUTE_RUNTIME_REGISTRY[name] = factory


def list_compute_runtimes() -> tuple[str, ...]:
    """Return the names of all registered compute runtimes."""
    return tuple(sorted(COMPUTE_RUNTIME_REGISTRY))


def get_compute_runtime() -> ComputeRuntime:
    """Return the singleton compute runtime.

    Defaults to :class:`InProcessComputeRuntime`. Custom runtimes
    can be installed ahead of the first call via
    :func:`set_compute_runtime`.
    """
    global SINGLETON
    if SINGLETON is None:
        SINGLETON = InProcessComputeRuntime()
    return SINGLETON


def set_compute_runtime(runtime: ComputeRuntime) -> None:
    """Replace the singleton compute runtime.

    Used by application bootstrap to install a configured runtime
    before the first :func:`get_compute_runtime` call.
    """
    global SINGLETON
    SINGLETON = runtime


def reset_compute_runtime() -> None:
    """Clear the singleton compute runtime (for tests)."""
    global SINGLETON
    SINGLETON = None
