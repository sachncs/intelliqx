"""Learning Agent (Tier 2).

Closes the feedback loop: after every run, agents report
``(prompt_id, outcome)`` to this agent. The agent aggregates
feedback and emits recommendations:

* ``deprecate`` — a prompt with pass rate below 60% over at least
  5 runs.
* ``promote_as_default`` — a prompt with pass rate ≥ 90% over at
  least 20 runs.

The thresholds are conservative; they exist to surface
clearly-broken or clearly-winning prompts without spamming the
orchestrator with low-confidence recommendations.

Persistence: feedback blobs are stored in the state store under
``learning:{tenant_id}:{run_id}`` with a 30-day TTL. The agent
re-reads them every time ``run`` is called, so the aggregation is
always over the current view of the data.

This module used to expose a small ``idx_doc`` shim for legacy
importers; that shim has been removed (no callers remain).
"""

from __future__ import annotations

import json
from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_state.store import get_state_store
from pydantic import BaseModel, ConfigDict, Field


class LearningInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    run_id: str
    feedback: dict[str, Any] = Field(default_factory=dict)
    # feedback examples:
    #   {"prompt_id": "v3", "outcome": "passed"}
    #   {"plan_node": "execution", "healed": True, "outcome": "passed"}


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str
    action: str
    rationale: str


class LearningOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendations: list[Recommendation] = Field(default_factory=list)


class LearningAgent(AgentBase):
    META = AgentMeta(
        name="learning",
        tier=2,
        version="0.1.0",
        description="Improves prompts, plans, and healing from history.",
    )
    INPUT_MODEL = LearningInput
    OUTPUT_MODEL = LearningOutput

    @traced_agent("learning")
    async def run(self, ctx: AgentContext, input: LearningInput) -> LearningOutput:
        state = get_state_store()
        # Persist this run's feedback. The state-store key encodes
        # the run id so re-runs of the same run don't double-count.
        feedback_key = f"learning:{input.tenant_id}:{input.run_id}"
        await state.set(
            feedback_key, json.dumps(input.feedback).encode("utf-8"), ttl_seconds=86400 * 30
        )

        # Aggregate pass/fail per prompt_id. The state store yields
        # every key with the ``learning:{tenant_id}:`` prefix; we
        # parse each blob (str-encoded dict) and tally the
        # ``outcome`` field.
        prompt_stats: dict[str, dict[str, int]] = {}
        async for k in state.keys(f"learning:{input.tenant_id}:"):
            try:
                blob = await state.get(k)
                if not blob:
                    continue
                data = json.loads(blob.decode("utf-8"))
            except Exception:
                # Malformed feedback is skipped (not fatal).
                continue
            pid = data.get("prompt_id")
            if pid:
                ps = prompt_stats.setdefault(pid, {"passed": 0, "failed": 0})
                if data.get("outcome") == "passed":
                    ps["passed"] += 1
                elif data.get("outcome") == "failed":
                    ps["failed"] += 1

        recommendations: list[Recommendation] = []
        for pid, stats in prompt_stats.items():
            total = stats["passed"] + stats["failed"]
            if total >= 5:
                rate = stats["passed"] / total
                if rate < 0.6:
                    recommendations.append(
                        Recommendation(
                            target=f"prompt:{pid}",
                            action="deprecate",
                            rationale=f"Pass rate {rate:.0%} below 60%",
                        )
                    )
                elif rate >= 0.9 and total >= 20:
                    recommendations.append(
                        Recommendation(
                            target=f"prompt:{pid}",
                            action="promote_as_default",
                            rationale=f"Pass rate {rate:.0%} over 20 runs",
                        )
                    )

        return LearningOutput(recommendations=recommendations)
