"""Risk Assessment Agent (Intelligence).

Combines three signals into a single 0..1 risk score and a priority
label (low / medium / high / critical):

* **Priority** — mean of requirement priority weights
  (``critical=0.9, high=0.6, medium=0.3, low=0.1``). Weight 0.5.
* **File ratio** — ``min(1.0, |affected_files| / 50)``. Weight 0.3.
* **History** — ``min(1.0, |historical_defects| / 20)``. Weight 0.2.

The score is the weighted sum, clamped to ``[0, 1]``. Priority
labels are derived from the score:

* ``>= 0.75`` → ``"critical"``
* ``>= 0.50`` → ``"high"``
* ``>= 0.25`` → ``"medium"``
* else       → ``"low"``

The weights were tuned against a small corpus of historical IntelliqX
releases; production deployments should re-calibrate by capturing
the post-release incident rate per ``priority`` band.
"""

from __future__ import annotations

from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory
from pydantic import BaseModel, ConfigDict, Field

from agents.intelligence.models import RiskScore


class RiskAssessmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[dict[str, Any]] = Field(default_factory=list)
    affected_files: list[str] = Field(default_factory=list)
    historical_defects: list[dict[str, Any]] = Field(default_factory=list)


class RiskAssessmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: RiskScore


def _priority_to_weight(p: str) -> float:
    """Map a priority label to its 0..1 weight.

    Unknown labels default to ``"medium"`` (0.3) so the score is
    never NaN.
    """
    return {"low": 0.1, "medium": 0.3, "high": 0.6, "critical": 0.9}.get(p, 0.3)


class RiskAssessmentAgent(AgentBase):
    META = AgentMeta(
        name="risk_assessment",
        category=AgentCategory.INTELLIGENCE,
        version="0.1.0",
        description="Computes a release risk score from requirements, code impact, and history.",
    )
    INPUT_MODEL = RiskAssessmentInput
    OUTPUT_MODEL = RiskAssessmentOutput

    @traced_agent("risk_assessment")
    async def run(self, ctx: AgentContext, input: RiskAssessmentInput) -> RiskAssessmentOutput:
        # Component 1: priority-weighted requirements score
        if input.requirements:
            avg_priority = sum(
                _priority_to_weight(r.get("priority", "medium")) for r in input.requirements
            ) / len(input.requirements)
        else:
            avg_priority = 0.3

        # Component 2: affected-file ratio (more files = higher risk)
        file_ratio = min(1.0, len(input.affected_files) / 50.0)

        # Component 3: historical defect count
        hist = min(1.0, len(input.historical_defects) / 20.0)

        # Weighted sum
        score = 0.5 * avg_priority + 0.3 * file_ratio + 0.2 * hist
        score = max(0.0, min(1.0, score))

        if score >= 0.75:
            priority = "critical"
            impact = (
                "High — likely to cause production incidents; block release without mitigation."
            )
        elif score >= 0.5:
            priority = "high"
            impact = "Elevated — schedule additional regression and review."
        elif score >= 0.25:
            priority = "medium"
            impact = "Moderate — standard release process applies."
        else:
            priority = "low"
            impact = "Low — fast-track eligible."

        factors = [
            f"avg_requirement_priority={avg_priority:.2f}",
            f"affected_files_ratio={file_ratio:.2f}",
            f"historical_defect_density={hist:.2f}",
        ]

        return RiskAssessmentOutput(
            score=RiskScore(score=score, priority=priority, business_impact=impact, factors=factors)
        )
