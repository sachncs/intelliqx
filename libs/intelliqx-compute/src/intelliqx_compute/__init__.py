"""Compute runtime abstraction for IntelliqX.

The platform separates the *what* of agent invocation (the
:mod:`intelliqx_agents` framework) from the *where* (this package). The
:class:`ComputeRuntime` interface is the same in every environment;
the implementation changes between local dev (in-process) and
production (Lambda, Cloud Functions, Modal Functions).

Adapters:

* :class:`InProcessComputeRuntime` — runs handlers in the same event
  loop. Default for tests and local dev.
* :class:`AWSLambdaComputeRuntime` — invokes ``intelliqx-{agent_name}``
  Lambda functions synchronously.
* :class:`GCPFunctionsComputeRuntime` — POSTs to
  ``https://{region}-{project}.cloudfunctions.net/intelliqx-{agent_name}``.
* :class:`ModalComputeRuntime` — calls ``modal.Function.remote()``.

The runtime is the natural integration point for retries, circuit
breakers, and per-invocation metrics; the in-process implementation
already exposes invocation duration via the metrics layer.
"""

from intelliqx_compute.runtime import (
    ComputeRuntime,
    InProcessComputeRuntime,
    InvocationRequest,
    InvocationResponse,
    get_compute_runtime,
)

__all__ = [
    "ComputeRuntime",
    "InProcessComputeRuntime",
    "InvocationRequest",
    "InvocationResponse",
    "get_compute_runtime",
]
