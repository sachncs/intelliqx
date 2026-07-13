"""Observability Agent (Governance).

Aggregates in-process metrics and checks SLA compliance. The
agent does not collect new data; it reads from
:class:`intelliqx_observability.metrics.MetricsRegistry` and applies the
default SLA targets.

Default SLA targets:

* ``agent_latency_ms`` — p95 must be ≤ 5000 ms.
* ``agent_success_rate`` — at least 95% of invocations succeed.

The two default SLAs are intentionally simple; production
deployments should override the values to match their contractual
SLOs. The agent's output includes a per-SLA compliance flag
suitable for inclusion in the Reporting agent's Markdown output.
"""

from __future__ import annotations

from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory
from intelliqx_observability.metrics import get_metrics
from pydantic import BaseModel, ConfigDict, Field


class ObservabilityInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    window_seconds: int = 3600


class SLARecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    target: float
    actual: float
    compliant: bool


class ObservabilityOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: dict[str, Any]
    slas: list[SLARecord] = Field(default_factory=list)


# SLA targets. The kind ("p95" or "rate") determines the
# compliance check direction: latency is "lower is better",
# success rate is "higher is better".
DEFAULT_SLAS: dict[str, tuple[str, float]] = {
    "agent_latency_ms": ("p95", 5000),
    "agent_success_rate": ("rate", 0.95),
}


class ObservabilityAgent(AgentBase):
    META = AgentMeta(
        name="observability",
        category=AgentCategory.GOVERNANCE,
        version="0.1.0",
        description="Aggregates metrics and checks SLA compliance.",
    )
    INPUT_MODEL = ObservabilityInput
    OUTPUT_MODEL = ObservabilityOutput

    @traced_agent("observability")
    async def run(self, ctx: AgentContext, input: ObservabilityInput) -> ObservabilityOutput:
        metrics = get_metrics()
        snapshot = metrics.snapshot()
        slas: list[SLARecord] = []
        for name, (kind, target) in DEFAULT_SLAS.items():
            actual = _extract_metric(snapshot, name, kind)
            slas.append(
                SLARecord(
                    name=name,
                    target=float(target),
                    actual=float(actual),
                    # Latency: lower is better. Success rate: higher
                    # is better.
                    compliant=actual <= target if kind == "p95" else actual >= target,
                )
            )
        return ObservabilityOutput(snapshot=snapshot, slas=slas)


def _extract_metric(snapshot: dict, name: str, kind: str) -> float:
    """Extract a metric value from the snapshot dict.

    The counters and histograms snapshot layout is
    ``{counter_name: {label_key: value}}``. The traversal therefore
    has two levels: metric name, then label key.
    """
    if name == "agent_latency_ms":
        hists = snapshot.get("histograms", {})
        for counter_name, label_dict in hists.items():
            if "duration" in counter_name.lower():
                for vals in label_dict.values():
                    if isinstance(vals, dict):
                        return vals.get("p95", 0.0)
        return 0.0
    if name == "agent_success_rate":
        counters = snapshot.get("counters", {})
        total = 0.0
        ok = 0.0
        for counter_name, label_dict in counters.items():
            for label_key, val in label_dict.items():
                total += val
                if "ok" in counter_name.lower() or "ok" in label_key.lower():
                    ok += val
        return ok / total if total > 0 else 1.0
    return 0.0
