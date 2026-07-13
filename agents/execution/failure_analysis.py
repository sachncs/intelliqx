"""Failure Analysis Agent (Execution).

Classifies a test failure into one of:

* ``"infra"``    — network/SSL/5xx, retrying may help.
* ``"product"``  — 4xx, assertion, ``expected`` mismatch, file a
  defect.
* ``"flake"``    — assertion/5xx with a passing history entry, suggest
  quarantine.
* ``"unknown"``  — anything else; manual triage.

The classifier is keyword-based — it scans the error string for
known tokens (``"connection"``, ``"timeout"``, ``"SSL"``, ``"404"``,
``"AssertionError"``, …) and picks the first matching bucket. The
flake detector adds a second pass: if the agent is given
``retry_count >= 1`` and at least one history entry shows
``"passed"``, the same error is reclassified as ``"flake"``.

The agent never raises; it always returns a
:class:`FailureOutput` so the orchestrator can branch on the
classification.
"""

from __future__ import annotations

from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory
from pydantic import BaseModel, ConfigDict, Field


class FailureInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    error: str
    test_name: str = ""
    history: list[dict[str, Any]] = Field(default_factory=list)
    retry_count: int = 0


class FailureOutput(BaseModel):
    """Output payload for the Failure Analysis agent.

    Attributes:
        classification: One of ``"infra"``, ``"product"``,
            ``"flake"``, ``"unknown"``.
        confidence: Calibrated confidence in the classification, in
            ``[0.0, 1.0]``. ``0.9`` for classified buckets, ``0.5``
            for ``"unknown"``.
        root_cause: Human-readable explanation of why the bucket was
            chosen.
        suggested_action: Recommended next step. Suitable for
            inclusion in a CI notification.
    """

    model_config = ConfigDict(extra="forbid")

    classification: str  # infra | product | flake | unknown
    confidence: float
    root_cause: str
    suggested_action: str


class FailureAnalysisAgent(AgentBase):
    META = AgentMeta(
        name="failure_analysis",
        category=AgentCategory.EXECUTION,
        version="0.1.0",
        description="Classifies test failures (infra / product / flake).",
    )
    INPUT_MODEL = FailureInput
    OUTPUT_MODEL = FailureOutput

    @traced_agent("failure_analysis")
    async def run(self, ctx: AgentContext, input: FailureInput) -> FailureOutput:
        err = (input.error or "").lower()
        retry = input.retry_count
        # Heuristic classification.
        if any(
            k in err for k in ("connection", "timeout", "econnrefused", "dns", "ssl", "503", "502")
        ):
            classification = "infra"
            root_cause = "Network/infrastructure failure"
            action = "Re-run on a fresh environment; check infra status"
        elif "404" in err or "401" in err or "403" in err:
            classification = "product"
            root_cause = "Auth or routing defect"
            action = "File a defect ticket with the failing URL and auth state"
        elif "500" in err or "AssertionError" in err or "expected" in err:
            # Could be product or flake; if a previous attempt
            # passed we treat it as flake.
            if retry >= 1 and _history_passes(input.history):
                classification = "flake"
                root_cause = "Intermittent failure"
                action = "Investigate flakiness; consider quarantine"
            else:
                classification = "product"
                root_cause = "Application error / assertion failure"
                action = "File a defect; attach reproduction"
        else:
            classification = "unknown"
            root_cause = "Unclassified error"
            action = "Manual triage"

        # Confidence: high when we have a clean classification,
        # low when the bucket is ``"unknown"``.
        confidence = 0.9 if classification != "unknown" else 0.5
        return FailureOutput(
            classification=classification,
            confidence=confidence,
            root_cause=root_cause,
            suggested_action=action,
        )


def _history_passes(history: list[dict]) -> bool:
    """Return ``True`` if at least one prior attempt passed (flake signature)."""
    return any(h.get("status") == "passed" for h in history)
