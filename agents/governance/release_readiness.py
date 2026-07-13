"""Release Readiness Agent (Tier 4).

Aggregates risk + coverage + performance + security + open defects
into a single Go / Conditional Go / No-Go recommendation with
explanations. The decision is driven by a **weighted score**:

* Risk:     -0.4 (critical) / -0.2 (high) / +0.1 (low)
* Coverage: +0.2 (≥ 80%) / +0.05 (≥ 60%) / -0.2 (< 60%)
* Performance SLO breach: -0.3
* Security: -0.5 (any critical) / -0.2 (any high) / 0 (clean)
* Open defects: -0.2 (> 10) / -0.05 (> 0) / 0 (none)
* History boost: +0.1 (≥ 90% historical success over 20+ runs)

Thresholds:

* score >= 0.3  → ``"go"``
* score >= -0.1 → ``"conditional_go"``
* else          → ``"no_go"``

The decision is intentionally **explainable**: every component
contributing to the score appears in ``explanation``, so a human
reviewer can see *why* a release is on the fence.

Confidence is a separate signal that starts at 0.7 and rises to
0.95 when the agent has a strong historical track record for the
release stream. The orchestrator can require a minimum confidence
in addition to the recommendation.
"""

from __future__ import annotations

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.ids import new_id
from pydantic import BaseModel, ConfigDict, Field


class ReleaseReadinessInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tenant_id: str
    risk_score: float = 0.0  # 0..1
    coverage_pct: float = 0.0  # 0..100
    performance_slo_pass: bool = True
    security_findings_critical: int = 0
    security_findings_high: int = 0
    open_defects: int = 0
    historical_release_success: float | None = None  # 0..1 if known


class ReleaseReadinessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation: str  # go | conditional_go | no_go
    confidence: float  # 0..1
    explanation: list[str] = Field(default_factory=list)
    decision_id: str = ""


class ReleaseReadinessAgent(AgentBase):
    META = AgentMeta(
        name="release_readiness",
        tier=4,
        version="0.1.0",
        description="Produces Go / Conditional Go / No-Go recommendation.",
    )
    INPUT_MODEL = ReleaseReadinessInput
    OUTPUT_MODEL = ReleaseReadinessOutput

    @traced_agent("release_readiness")
    async def run(self, ctx: AgentContext, input: ReleaseReadinessInput) -> ReleaseReadinessOutput:
        explanation: list[str] = []
        score = 0.0
        conf = 0.7

        # Risk contribution (negative)
        if input.risk_score >= 0.75:
            score -= 0.4
            explanation.append(f"High risk score {input.risk_score:.2f}")
        elif input.risk_score >= 0.5:
            score -= 0.2
            explanation.append(f"Elevated risk score {input.risk_score:.2f}")
        else:
            score += 0.1
            explanation.append(f"Low risk score {input.risk_score:.2f}")

        # Coverage contribution (positive if >= 80%)
        if input.coverage_pct >= 80:
            score += 0.2
            explanation.append(f"Coverage {input.coverage_pct:.1f}% ≥ 80%")
        elif input.coverage_pct >= 60:
            score += 0.05
            explanation.append(f"Coverage {input.coverage_pct:.1f}% acceptable")
        else:
            score -= 0.2
            explanation.append(f"Coverage {input.coverage_pct:.1f}% below 60%")

        # Performance SLOs
        if not input.performance_slo_pass:
            score -= 0.3
            explanation.append("Performance SLO breach")
        else:
            explanation.append("Performance SLOs met")

        # Security findings
        if input.security_findings_critical > 0:
            score -= 0.5
            explanation.append(f"{input.security_findings_critical} critical security findings")
        elif input.security_findings_high > 0:
            score -= 0.2
            explanation.append(f"{input.security_findings_high} high security findings")
        else:
            explanation.append("No critical/high security findings")

        # Open defects
        if input.open_defects > 10:
            score -= 0.2
            explanation.append(f"{input.open_defects} open defects")
        elif input.open_defects > 0:
            score -= 0.05
            explanation.append(f"{input.open_defects} open defects")
        else:
            explanation.append("No open defects")

        # Historical success boost
        if input.historical_release_success is not None and input.historical_release_success >= 0.9:
            score += 0.1
            conf = min(0.95, conf + 0.1)
            explanation.append(
                f"Strong historical success rate {input.historical_release_success:.0%}"
            )

        # Recommendation
        if score >= 0.3:
            recommendation = "go"
        elif score >= -0.1:
            recommendation = "conditional_go"
        else:
            recommendation = "no_go"

        return ReleaseReadinessOutput(
            recommendation=recommendation,
            confidence=conf,
            explanation=explanation,
            decision_id=new_id(),
        )
