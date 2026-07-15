"""Agent base class and runtime context.

The :class:`AgentBase` is a generic ``Generic[InputT, OutputT]`` so
each subclass gets strongly-typed ``run`` and ``invoke`` signatures.
The ``INPUT_MODEL`` and ``OUTPUT_MODEL`` class attributes are
Pydantic models that drive the default ``invoke`` implementation:
``request.input`` is validated against ``INPUT_MODEL``, the agent's
``run`` is awaited, and the result is serialised via
``OUTPUT_MODEL.model_dump(mode="json")``.

Subclasses that need polymorphic dispatch (one input model, many
behaviours) override ``invoke`` directly. See the Memory Manager
agent for an example.
"""

from __future__ import annotations

import abc
from collections.abc import Callable
from typing import Any, ClassVar, Generic, TypeVar

from intelliqx_compute.runtime import InvocationRequest
from intelliqx_core.models import AgentCapability, AgentCategory, TenantContext
from intelliqx_observability.logging import get_logger
from intelliqx_observability.metrics import get_metrics
from intelliqx_observability.tracing import get_tracer
from pydantic import BaseModel, ConfigDict, Field

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class AgentMeta(BaseModel):
    """Static metadata for an agent.

    Defined once per agent class as the ``META`` class attribute.
    The platform reads it for marketplace listings, health
    endpoints, and capability-based routing.

    Attributes:
        name: Registry key. Must be unique within a process.
        category: Functional category — coordination, intelligence,
            execution, or governance. Maps 1-to-1 to the agent
            subdirectory under ``agents/``.
        version: SemVer string. Marketplace agents may pin to a
            specific version.
        description: One-line summary; used in logs and
            marketplace listings.
        capabilities: List of advertised capabilities for
            discovery.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    category: AgentCategory
    version: str = "0.1.0"
    description: str = ""
    capabilities: list[AgentCapability] = Field(default_factory=list)


class AgentContext(BaseModel):
    """The runtime context passed to every agent invocation.

    Attributes:
        tenant: The active :class:`~intelliqx_core.models.TenantContext`.
        run_id: The orchestrator's run id (or ``"unknown"`` for
            ad-hoc invocations).
        trace_id: Optional OTel trace id for cross-agent
            correlation.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    tenant: TenantContext
    run_id: str
    trace_id: str | None = None


class AgentBase(abc.ABC, Generic[InputT, OutputT]):
    """Base class for all agents.

    Subclasses must:
        * declare ``META`` (an :class:`AgentMeta`).
        * declare ``INPUT_MODEL`` and ``OUTPUT_MODEL`` (Pydantic models).
        * implement ``async run(ctx, input) -> output``.

    Subclasses that need polymorphic dispatch override ``invoke``.
    """

    META: ClassVar[AgentMeta]

    def __init__(self) -> None:
        # Per-instance handles; cheap to construct.
        self.logger = get_logger(self.__class__.__name__)
        self.metrics = get_metrics()
        self.tracer = get_tracer()

    @abc.abstractmethod
    async def run(self, ctx: AgentContext, input: InputT) -> OutputT:
        """Implement the agent's behaviour.

        Args:
            ctx: The runtime context (tenant + run id).
            input: The validated input model instance.

        Returns:
            The output model instance.
        """
        raise NotImplementedError

    async def invoke(self, request: InvocationRequest) -> dict[str, Any]:
        """Default invocation entry point.

        Validates ``request.input`` against ``INPUT_MODEL``,
        constructs an :class:`AgentContext` from the request metadata,
        and calls ``self.run``. The result is serialised via
        ``OUTPUT_MODEL.model_dump(mode="json")`` so it can cross the
        compute boundary unchanged.

        Agents that need a different input/output mapping (e.g. the
        Memory Manager) override this method.
        """

        input_model = getattr(self, "INPUT_MODEL", None)
        output_model = getattr(self, "OUTPUT_MODEL", None)
        if input_model is None or output_model is None:
            raise RuntimeError(
                f"{self.__class__.__name__} must declare INPUT_MODEL and OUTPUT_MODEL"
            )
        inp = input_model.model_validate(request.input)
        ctx = AgentContext(
            tenant=TenantContext(
                tenant_id=request.tenant_id, trace_id=request.metadata.get("trace_id")
            ),
            run_id=request.metadata.get("run_id", "unknown"),
        )
        out = await self.run(ctx, inp)
        return out.model_dump(mode="json")

    @classmethod
    def capability(cls) -> AgentCapability:
        """Return a basic :class:`AgentCapability` derived from ``META``.

        Subclasses may override to attach richer metadata (input
        schemas, SLAs, cost ceilings).
        """
        m = cls.META
        return AgentCapability(name=m.name, description=m.description)


AgentFactory = Callable[[], AgentBase]
"""Type alias for an agent factory.

Factories are stored in the registry (not instances) so each
invocation gets a fresh, stateless agent.
"""
