"""Compute runtime abstraction for IntelliqX.

The platform separates the *what* of agent invocation (the
:mod:`intelliqx_agents` framework) from the *where* (this package). The
:class:`ComputeRuntime` interface is the same in every environment;
the in-process implementation runs handlers directly in the same event
loop as the caller.

Adapters:

* :class:`InProcessComputeRuntime` — runs handlers in the same event
  loop. Default for tests and local dev.

The runtime is the natural integration point for retries, circuit
breakers, and per-invocation metrics; the in-process implementation
already exposes invocation duration via the metrics layer.
"""

from intelliqx_compute.runtime import (
    COMPUTE_RUNTIME_REGISTRY,
    ComputeRuntime,
    InProcessComputeRuntime,
    InvocationRequest,
    InvocationResponse,
    get_compute_runtime,
    list_compute_runtimes,
    register_compute_runtime,
)

__all__ = [
    "COMPUTE_RUNTIME_REGISTRY",
    "ComputeRuntime",
    "InProcessComputeRuntime",
    "InvocationRequest",
    "InvocationResponse",
    "get_compute_runtime",
    "list_compute_runtimes",
    "register_compute_runtime",
]
