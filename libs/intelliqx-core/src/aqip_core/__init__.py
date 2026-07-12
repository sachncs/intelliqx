"""AQIP shared core.

Provides the value objects, enums, error hierarchy, and event envelope
primitives used by every other AQIP library and every agent.

The core is intentionally tiny and dependency-free (only Pydantic and the
ULID library). Higher-level libraries (``aqip-events``, ``aqip-state``,
``aqip-storage`` …) build on these primitives.

Design notes:

* All public models use ``extra="forbid"`` so unexpected fields surface as
  validation errors at the boundary instead of silently propagating through
  the system.
* ``TenantContext`` is **frozen** to make it hashable and to prevent
  accidental mutation across an agent's lifetime.
* Identifiers are 26-character Crockford-base32 ULIDs (see ``ids.py``).
  They are lexicographically sortable by creation time, which makes event
  streams and audit logs self-ordering without extra metadata.
* The error hierarchy is rooted at ``AQIPError`` so callers may catch the
  whole family with a single ``except`` while still being able to
  distinguish specific failure modes by their concrete type.
"""

from aqip_core.errors import (
    AQIPError,
    CloudConfigError,
    ContractError,
    NotFoundError,
    ValidationError,
)
from aqip_core.events import BaseEvent, EventEnvelope, EventMetadata
from aqip_core.ids import is_valid_id, new_id, parse_id
from aqip_core.models import (
    AgentCapability,
    AgentRef,
    CloudProvider,
    Goal,
    HealthStatus,
    PlanNode,
    RunStatus,
    TenantContext,
)

__all__ = [
    "AQIPError",
    "AgentCapability",
    "AgentRef",
    "BaseEvent",
    "CloudConfigError",
    "CloudProvider",
    "ContractError",
    "EventEnvelope",
    "EventMetadata",
    "Goal",
    "HealthStatus",
    "NotFoundError",
    "PlanNode",
    "RunStatus",
    "TenantContext",
    "ValidationError",
    "is_valid_id",
    "new_id",
    "parse_id",
]
