"""Event base classes for IntelliqX.

The event system is the cross-agent backbone of the platform. Every
event carries an :class:`EventMetadata` envelope (tenant ID, producer,
correlation/causation IDs, schema version) so events can be traced,
audited, and routed deterministically.

Key concepts:

* ``detail_type`` is the topic name (e.g. ``"PlanNodeCompleted"``,
  ``"RunStarted"``). The EventRegistry validates published payloads
  against the registered JSON Schema for that topic when ``jsonschema``
  is installed.
* ``EventEnvelope`` is the wire-level wrapper used to carry a
  strongly-typed payload around the platform. The envelope is a thin
  shell around the event payload.
* ``schema_version`` defaults to ``"1.0"`` and should be bumped when
  the payload shape changes in a breaking way. Consumers are
  responsible for handling older versions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from intelliqx_core.ids import new_id

T = TypeVar("T", bound=BaseModel)


class EventMetadata(BaseModel):
    """Metadata attached to every event.

    The metadata is the only thing every event payload is guaranteed to
    share, so cross-cutting consumers (audit, tracing, governance)
    should depend on this shape and nothing else.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=new_id)
    tenant_id: str
    correlation_id: str | None = None
    causation_id: str | None = None
    produced_by: str
    schema_version: str = "1.0"
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BaseEvent(BaseModel):
    """Base class for all events.

    Subclasses set ``detail_type`` as a class-level literal so the topic
    name is discoverable from the class itself. Use ``BaseEvent`` as the
    parameter type for handlers that don't care about the concrete
    payload shape.
    """

    model_config = ConfigDict(extra="forbid")

    detail_type: str
    metadata: EventMetadata


class EventEnvelope(BaseModel, Generic[T]):
    """Generic envelope carrying an event payload.

    It is intentionally separate from ``BaseEvent`` so the generic
    parameter can be used to type the payload at the handler
    boundary while the envelope itself remains uniform.
    """

    model_config = ConfigDict(extra="forbid")

    detail_type: str
    payload: dict[str, Any]
    metadata: EventMetadata

    @classmethod
    def from_event(cls, event: T, metadata: EventMetadata) -> EventEnvelope[T]:
        """Wrap a strongly-typed event in an envelope.

        Args:
            event: The event instance to wrap.
            metadata: The metadata to attach. Typically produced by
                ``agents.coordination.events.make_metadata``.

        Returns:
            A new ``EventEnvelope`` whose ``detail_type`` is the event
            class name and whose ``payload`` is the JSON-serialised
            event (mode ``"json"``).
        """
        return cls(
            detail_type=event.__class__.__name__,
            payload=event.model_dump(mode="json"),
            metadata=metadata,
        )
