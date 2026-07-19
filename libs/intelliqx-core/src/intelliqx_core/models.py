"""Shared Pydantic models for IntelliqX.

Every model in this module uses ``extra="forbid"`` by default to keep the
platform's input boundary explicit: unknown fields fail validation rather
than being silently dropped or propagated. Models that opt out of strict
validation (e.g. because the producer is the LLM and over-generation is
expected) do so explicitly via ``ConfigDict(extra="ignore")``.

Models documented here:

* Enums: :class:`RunStatus`, :class:`HealthStatus`
* Capability contracts: :class:`AgentCapability`, :class:`AgentRef`
* Runtime context: :class:`TenantContext` (frozen)
* Workflow input/output: :class:`Goal`, :class:`PlanNode`
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(str, Enum):
    """Lifecycle status of a workflow run.

    The status is published on the ``run.completed`` event and persisted
    to the state store at ``run:{run_id}``. Allowed transitions::

        PENDING -> RUNNING -> SUCCEEDED
                          -> FAILED
                          -> CANCELLED
                          -> PAUSED -> (RUNNING | CANCELLED)
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


class HealthStatus(str, Enum):
    """Health status of an agent or service.

    Reported by health endpoints and aggregated by the Observability
    Agent. ``DEGRADED`` indicates the entity is functional but with
    reduced capacity (e.g. partial outage, elevated error rate).
    """

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class AgentCategory(str, Enum):
    """Functional category of an IntelliqX agent.

    Categories are descriptive — they map 1-to-1 to the four top-level
    agent directories (``agents/coordination``, ``agents/intelligence``,
    ``agents/execution``, ``agents/governance``) and replace the older
    numeric ``tier`` field. Order in the enum mirrors the platform's
    dependency graph: coordination orchestrates everything, then
    intelligence decides, execution runs, and governance observes.
    """

    COORDINATION = "coordination"
    INTELLIGENCE = "intelligence"
    EXECUTION = "execution"
    GOVERNANCE = "governance"


class AgentCapability(BaseModel):
    """Describes an agent's input/output contract and operational limits.

    Used by the marketplace and discovery layer. Fields are optional
    so that minimal registrations (just ``name`` + ``description``) are
    still well-formed.
    """

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    cost_ceiling_usd: float | None = None
    latency_sla_ms: int | None = None


class AgentRef(BaseModel):
    """Reference to a registered agent.

    Used in marketplace manifests and in intelligence/execution agent
    outputs that need to cite another agent by name without binding
    to a specific class import. The ``version`` field enables
    side-by-side deployments during agent rollouts.
    """

    name: str
    category: AgentCategory
    version: str = "0.1.0"


class TenantContext(BaseModel):
    """Tenant context propagated through every agent invocation.

    Frozen so the context cannot be mutated mid-flight. Carries:

    * ``tenant_id`` — the authoritative isolation key.
    * ``user_id``  — the end-user (or service principal) that initiated
      the call; ``None`` for system-initiated work.
    * ``roles``    — tuple of role names (e.g. ``("admin", "operator")``)
      used by the Governance agent for RBAC checks.
    * ``trace_id`` — OTel trace identifier for cross-agent correlation.
    """

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    user_id: str | None = None
    roles: tuple[str, ...] = ()
    trace_id: str | None = None


class Goal(BaseModel):
    """A business goal submitted to the platform.

    Goals are the platform's primary unit of work. The Planner agent
    consumes a :class:`Goal` and produces an :class:`ExecutionPlan` from
    it. The ``kind`` field drives plan-template selection (see
    ``agents/coordination/templates.py``); ``inputs`` and ``constraints`` are
    forwarded to the plan and the individual nodes.
    """

    model_config = ConfigDict(extra="forbid")

    goal_id: str
    tenant_id: str
    kind: str  # e.g. "release.readiness.requested", "analyze_prd", "run_tests"
    description: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PlanNode(BaseModel):
    """A single node in an execution-plan DAG.

    Nodes form a DAG via ``depends_on``; the Orchestrator performs a
    Kahn-style topological sort and runs independent nodes in parallel
    up to ``max_parallel``. ``timeout_seconds`` and ``retry_policy`` are
    enforced per-node, not per-plan.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    agent: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    timeout_seconds: int = 300
    retry_policy: dict[str, Any] = Field(default_factory=dict)
