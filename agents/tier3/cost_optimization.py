"""Cost Optimization Agent (Tier 3).

Analyzes run history (via the in-process metrics registry) and
emits recommendations to reduce spend. The current heuristics:

1. **Batch small invocations.** When the total invocation count is
   non-trivial, the agent estimates the per-invocation overhead and
   suggests batching to amortise it.
2. **Spot instances for long-tail latency.** When a histogram's
   ``p99 / p50`` ratio exceeds 5x, the long tail is probably
   running on slow on-demand instances; switching to spot saves
   money.
3. **Quarantine flaky tests.** When the number of failed runs is
   high, the agent flags the suite for quarantine to avoid
   rerun-amplified cost.

The recommendations are **heuristic**. They produce reasonable
starting points but are not a substitute for actual cost
analysis (Vantage, Cloudability, etc.). Production deployments
should treat the output as a triage list, not a bill.
"""

from __future__ import annotations

from aqip_agents.base import AgentBase, AgentContext, AgentMeta
from aqip_agents.decorators import traced_agent
from aqip_observability.metrics import get_metrics
from pydantic import BaseModel, ConfigDict, Field


class CostOptInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tenant_id: str
    window_days: int = 30


class CostRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str
    action: str
    estimated_savings_usd: float = 0.0
    rationale: str


class CostOptOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendations: list[CostRecommendation] = Field(default_factory=list)
    estimated_total_savings_usd: float = 0.0


class CostOptimizationAgent(AgentBase):
    META = AgentMeta(
        name="cost_optimization",
        tier=3,
        version="0.1.0",
        description="Recommends compute right-sizing and scheduling.",
    )
    INPUT_MODEL = CostOptInput
    OUTPUT_MODEL = CostOptOutput

    @traced_agent("cost_optimization")
    async def run(self, ctx: AgentContext, input: CostOptInput) -> CostOptOutput:
        snap = get_metrics().snapshot()
        recs: list[CostRecommendation] = []

        # Heuristic 1: count total invocations and recommend
        # batching when the count is non-trivial.
        counters = snap.get("counters", {})
        total_invocations = sum(sum(v.values()) for v in counters.values())
        if total_invocations > 0:
            recs.append(
                CostRecommendation(
                    target="scheduler",
                    action="batch_small_invocations",
                    estimated_savings_usd=round(total_invocations * 0.0001, 2),
                    rationale=f"{total_invocations} invocations detected; batching may reduce per-invocation overhead",
                )
            )

        # Heuristic 2: histograms with high p99 vs p50 → spot
        # instances for long-tail.
        for name, label_dict in snap.get("histograms", {}).items():
            for vals in label_dict.values():
                if not isinstance(vals, dict):
                    continue
                p50 = vals.get("p50", 0)
                p99 = vals.get("p99", 0)
                if p50 > 0 and p99 / max(p50, 1) > 5:
                    recs.append(
                        CostRecommendation(
                            target=f"histogram:{name}",
                            action="use_spot_for_long_tail",
                            estimated_savings_usd=round((p99 - p50) * 0.001, 2),
                            rationale=f"{name} p99/p50 ratio > 5 — long-tail latency suggests spot migration",
                        )
                    )

        # Heuristic 3: many failed runs → quarantine flaky tests.
        failed = sum(
            v for d in counters.values() for v in d.values() if "fail" in str(d).lower()
        )
        if failed > 10:
            recs.append(
                CostRecommendation(
                    target="ci",
                    action="quarantine_flaky",
                    estimated_savings_usd=round(failed * 0.5, 2),
                    rationale=f"{failed} failed runs detected; quarantine to reduce rerun cost",
                )
            )

        total_savings = sum(r.estimated_savings_usd for r in recs)
        return CostOptOutput(recommendations=recs, estimated_total_savings_usd=total_savings)
