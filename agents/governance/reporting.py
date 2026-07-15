"""Reporting Agent (Governance).

Produces Markdown and JSON run reports. The Markdown output is
designed to be PR-comment friendly: a heading, a one-line summary,
and a metrics snapshot section. The JSON output mirrors the
Markdown shape so downstream consumers (Slack bot, GitHub bot,
release dashboard) can render their own view.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory
from intelliqx_observability.metrics import get_metrics
from pydantic import BaseModel, ConfigDict, Field


class ReportingInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str
    tenant_id: str
    summary: dict[str, Any] = Field(default_factory=dict)
    include_metrics: bool = True


class ReportingOutput(BaseModel):
    """Output payload for the Reporting agent.

    Attributes:
        markdown: PR-comment-friendly Markdown rendering of the run.
        json_payload: Machine-readable mirror of the Markdown
            content, suitable for downstream consumers (Slack bot,
            GitHub bot, release dashboard).
        summary: Echo of the input summary, for convenient access.
    """

    model_config = ConfigDict(extra="forbid")

    markdown: str
    json_payload: dict[str, Any]
    summary: dict[str, Any] = Field(default_factory=dict)


class ReportingAgent(AgentBase):
    META = AgentMeta(
        name="reporting",
        category=AgentCategory.GOVERNANCE,
        version="0.1.0",
        description="Generates executive + engineering reports.",
    )
    INPUT_MODEL = ReportingInput
    OUTPUT_MODEL = ReportingOutput

    # Maximum characters per metrics section in the Markdown
    # output. Beyond this we truncate with an ellipsis to keep
    # PR comments readable.
    METRICS_SECTION_MAX_CHARS: int = 1000

    @traced_agent("reporting")
    async def run(self, ctx: AgentContext, input: ReportingInput) -> ReportingOutput:
        metrics_snapshot = get_metrics().snapshot() if input.include_metrics else {}
        md = render_markdown(input, metrics_snapshot, max_chars=self.METRICS_SECTION_MAX_CHARS)
        js = {
            "run_id": input.run_id,
            "tenant_id": input.tenant_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": input.summary,
            "metrics": metrics_snapshot,
        }
        return ReportingOutput(markdown=md, json_payload=js, summary=input.summary)


def render_markdown(input: ReportingInput, metrics: dict, *, max_chars: int) -> str:
    """Render the Markdown report.

    Structure:

    * Title with the run id.
    * Tenant + generation timestamp.
    * Executive summary table (total / passed / failed).
    * Metrics snapshot (counters / gauges / histograms) if any.

    Args:
        input: The reporting input payload.
        metrics: Pre-computed metrics snapshot (``{}`` to omit the
            section).
        max_chars: Per-section character cap for the metrics
            snapshot. JSON dumps beyond this length are truncated
            so a noisy registry doesn't blow up the PR comment.

    Returns:
        The fully-rendered Markdown string.
    """
    summary = input.summary
    lines: list[str] = []
    lines.append(f"# IntelliqX Run Report — {input.run_id}")
    lines.append("")
    lines.append(f"- Tenant: `{input.tenant_id}`")
    lines.append(f"- Generated: {datetime.now(UTC).isoformat()}Z")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- Total runs: {summary.get('total', 'N/A')}")
    lines.append(f"- Passed: {summary.get('ok', 'N/A')}")
    lines.append(f"- Failed: {summary.get('failed', 'N/A')}")
    lines.append("")
    if metrics:
        lines.append("## Metrics Snapshot")
        lines.append("")
        for kind in ("counters", "gauges", "histograms"):
            if metrics.get(kind):
                lines.append(f"### {kind.title()}")
                lines.append("```json")
                # Truncate the JSON dump so a noisy metric registry
                # doesn't blow up the PR comment.
                lines.append(str(metrics[kind])[:max_chars])
                lines.append("```")
                lines.append("")
    return "\n".join(lines)
