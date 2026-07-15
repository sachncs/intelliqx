"""Coordination event types.

A small set of strongly-typed event payloads exchanged by the
Coordination agents. Every event carries :class:`intelliqx_core.events.EventMetadata`
so the platform can correlate them across processes and clouds.

Topic names are ``"<noun>.<verb>(.<modifier>)"`` — verb last so
publishers and subscribers line up under the same prefix. Examples:

* ``run.started`` / ``run.completed``
* ``plan.node.started`` / ``plan.node.completed``

The :func:`make_metadata` helper is the only call site most agents need.
"""

from __future__ import annotations

from typing import Any

from intelliqx_core.events import BaseEvent, EventMetadata
from intelliqx_core.models import RunStatus
from pydantic import Field


class PlanGenerated(BaseEvent):
    """Emitted by the Planner when an :class:`intelliqx_core.models.PlanNode` list is ready."""

    detail_type: str = "PlanGenerated"
    plan_id: str
    goal_id: str
    nodes: list[dict[str, Any]] = Field(default_factory=list)


class PlanNodeStarted(BaseEvent):
    """Emitted when the Orchestrator begins invoking a plan node's agent."""

    detail_type: str = "PlanNodeStarted"

    plan_id: str
    node_id: str
    agent: str


class PlanNodeCompleted(BaseEvent):
    """Emitted when the Orchestrator finishes invoking a plan node.

    Attributes:
        status: ``"ok"``, ``"timeout"``, ``"error"``, or ``"not_found"``.
        duration_ms: Wall-clock duration of the invocation.
        output: The agent's serialised output.
        error: Human-readable error message on failure.
    """

    detail_type: str = "PlanNodeCompleted"

    plan_id: str
    node_id: str
    agent: str
    status: str
    duration_ms: int = 0
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class RunStarted(BaseEvent):
    """Emitted by the Orchestrator when a workflow run begins."""

    detail_type: str = "RunStarted"

    run_id: str
    plan_id: str
    goal_id: str


class RunCompleted(BaseEvent):
    """Emitted by the Orchestrator when a workflow run terminates.

    ``status`` follows :class:`intelliqx_core.models.RunStatus`.
    ``summary`` carries per-node counts so subscribers can render a
    release-quality event without a second round-trip.
    """

    detail_type: str = "RunCompleted"

    run_id: str
    plan_id: str
    goal_id: str
    status: RunStatus
    summary: dict[str, Any] = Field(default_factory=dict)


class AgentInvocationStarted(BaseEvent):
    """Emitted by a per-invocation hook (compute runtime)."""

    detail_type: str = "AgentInvocationStarted"

    run_id: str
    agent: str


class AgentInvocationCompleted(BaseEvent):
    """Emitted by a per-invocation hook (compute runtime)."""

    detail_type: str = "AgentInvocationCompleted"

    run_id: str
    agent: str
    status: str
    duration_ms: int
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


def make_metadata(
    *, tenant_id: str, produced_by: str, correlation_id: str | None = None
) -> EventMetadata:
    """Build an :class:`EventMetadata` for an event produced by ``produced_by``.

    Args:
        tenant_id: The owning tenant.
        produced_by: The agent or service emitting the event
            (e.g. ``"orchestrator"``).
        correlation_id: Optional id to thread across multiple
            events in the same logical operation (e.g. a single
            goal → plan → run).
    """
    return EventMetadata(
        tenant_id=tenant_id, produced_by=produced_by, correlation_id=correlation_id
    )


__all__ = [
    "AgentInvocationCompleted",
    "AgentInvocationStarted",
    "PlanGenerated",
    "PlanNodeCompleted",
    "PlanNodeStarted",
    "RunCompleted",
    "RunStarted",
    "make_metadata",
]
