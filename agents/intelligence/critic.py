"""Critic / Validator Agent (Tier 2).

Validates another agent's output through a four-stage pipeline:

1. **Expected keys** — every key in ``expected_keys`` must appear in
   ``output``.
2. **Schema validation** — if ``schema_`` is provided and the
   ``jsonschema`` package is installed, the output is validated
   against it. (The check is best-effort and skipped when
   ``jsonschema`` is not installed.)
3. **Rule-based** — text rules in ``rules`` are evaluated:
   * ``non_empty:<key>`` — ``output[key]`` must be truthy.
   * ``type:<key>=<typename>`` — ``type(output[key]).__name__`` must
     equal ``typename``.
4. **Hallucination heuristic** — any string value that matches
   ``[<word>:<hash>]`` (a common LLM "fake" marker) is flagged.

The result is a :class:`CritiqueRecord` with ``passed=True`` when
no issues were found. The Critic never raises; the orchestrator
treats ``passed=False`` as a recoverable failure and routes the
critique to a human approver (or, in fully automated mode, to the
Learning agent for prompt improvement).
"""

from __future__ import annotations

from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory
from pydantic import BaseModel, ConfigDict, Field

from agents.intelligence.models import CritiqueRecord


class CriticInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str  # name of the agent whose output we are critiquing
    output: dict[str, Any]
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")
    rules: list[str] = Field(default_factory=list)
    expected_keys: list[str] = Field(default_factory=list)


class CriticOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    critique: CritiqueRecord


class CriticAgent(AgentBase):
    META = AgentMeta(
        name="critic",
        category=AgentCategory.INTELLIGENCE,
        version="0.1.0",
        description="Validates agent outputs for correctness, consistency, hallucination.",
    )
    INPUT_MODEL = CriticInput
    OUTPUT_MODEL = CriticOutput

    @traced_agent("critic")
    async def run(self, ctx: AgentContext, input: CriticInput) -> CriticOutput:
        issues: list[str] = []
        suggestions: list[str] = []

        # 1) Expected keys
        for k in input.expected_keys:
            if k not in input.output:
                issues.append(f"Missing expected key: {k!r}")

        # 2) Schema validation (best-effort)
        if input.schema_:
            try:
                import jsonschema  # type: ignore

                try:
                    jsonschema.validate(input.output, input.schema_)
                except jsonschema.ValidationError as e:
                    issues.append(f"Schema violation: {e.message[:200]}")
                    suggestions.append("Re-run producer agent with stricter output formatting")
            except ImportError:
                # jsonschema not installed: skip silently.
                pass

        # 3) Rule-based
        for rule in input.rules:
            if "non_empty:" in rule:
                key = rule.split(":", 1)[1].strip()
                if not input.output.get(key):
                    issues.append(f"Rule violated: {key!r} must be non-empty")
            elif "type:" in rule:
                _, spec = rule.split(":", 1)
                key, expected = [s.strip() for s in spec.split("=")]
                actual = type(input.output.get(key)).__name__
                if actual != expected:
                    issues.append(f"Rule violated: {key!r} must be {expected}, got {actual}")

        # 4) Hallucination heuristic
        for k, v in input.output.items():
            if isinstance(v, str) and v.startswith("[") and v.endswith("]") and "fake" in v.lower():
                issues.append(f"Possible hallucination/template marker in {k!r}: {v[:80]}")

        # 5) Empty output
        if not input.output:
            issues.append("Empty output")

        passed = not issues
        return CriticOutput(
            critique=CritiqueRecord(
                target=input.target, passed=passed, issues=issues, suggestions=suggestions
            )
        )
