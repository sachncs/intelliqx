"""Smoke agent: a minimal always-succeeding agent used for E2E tests.

The smoke agent exists to prove the end-to-end pipeline (Planner →
Orchestrator → compute runtime → agent invocation) without pulling
in any of the heavier Intelligence / Execution logic. Every test in Phase 1
and beyond uses it as the leaf node of a plan.
"""

from __future__ import annotations

from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory
from pydantic import BaseModel, ConfigDict


class SmokeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    marker: str = "hello"


class SmokeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    echo: str
    metadata: dict[str, Any] = {}


class SmokeAgent(AgentBase):
    """Always-succeeding test agent.

    Echoes the input ``marker`` back and records the tenant id in the
    output's ``metadata`` dict — useful for E2E tests that want to
    confirm a value survived the round-trip.
    """

    META = AgentMeta(
        name="smoke",
        category=AgentCategory.COORDINATION,
        description="Always-succeeding smoke agent for E2E tests.",
    )
    INPUT_MODEL = SmokeInput
    OUTPUT_MODEL = SmokeOutput

    @traced_agent("smoke")
    async def run(self, ctx: AgentContext, input: SmokeInput) -> SmokeOutput:
        return SmokeOutput(echo=input.marker, metadata={"tenant": ctx.tenant.tenant_id})
