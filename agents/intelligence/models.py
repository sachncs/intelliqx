"""Shared value objects for Intelligence agents.

These models are the structured outputs that the Intelligence agents
produce and the Execution/4 agents consume. They are deliberately
simple — flat structures with string severities so callers can
serialise them to JSON without a custom encoder.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RequirementsGraph(BaseModel):
    """Output of the Requirements Intel Agent.

    Attributes:
        requirements: One dict per requirement. At minimum each
            entry has ``id``, ``title``, ``priority``, and
            ``acceptance_criteria`` keys.
        traceability: Edges between requirements that share
            significant vocabulary. Each entry is
            ``{"from": req_id, "to": req_id, "shared_keywords": [...]}``.
    """

    model_config = ConfigDict(extra="forbid")

    requirements: list[dict[str, Any]] = Field(default_factory=list)
    traceability: list[dict[str, Any]] = Field(default_factory=list)


class CodeImpactGraph(BaseModel):
    """Output of the Code Intel Agent.

    Attributes:
        affected_files: Logical paths that should be re-tested given
            the current changes (including transitive dependents).
        dependencies: ``{"from": node_id, "to": node_id, "symbol": str}``
            edges describing the import graph.
        impact_summary: One-line human description of the analysis
            result; rendered into the Reporting agent's Markdown.
    """

    model_config = ConfigDict(extra="forbid")

    affected_files: list[str] = Field(default_factory=list)
    dependencies: list[dict[str, Any]] = Field(default_factory=list)
    impact_summary: str = ""


class RiskScore(BaseModel):
    """Output of the Risk Assessment Agent.

    Attributes:
        score: Aggregate risk score in ``[0.0, 1.0]``.
        priority: Severity bucket. One of ``"low"`` (< 0.25),
            ``"medium"`` (< 0.5), ``"high"`` (< 0.75),
            ``"critical"`` (>= 0.75).
        business_impact: Human-readable description of the
            recommended action for this priority band.
        factors: Per-component inputs that produced the score.
            Each entry is a ``"name=value"`` string suitable for
            inclusion in a release-decision audit log.
    """

    model_config = ConfigDict(extra="forbid")

    score: float  # 0-1
    priority: str  # low | medium | high | critical
    business_impact: str
    factors: list[str] = Field(default_factory=list)


class TestDesignOutput(BaseModel):
    """Output of the Test Design Agent.

    Attributes:
        tests: One dict per generated test. At minimum each entry
            has ``id``, ``type`` (``"functional"`` /
            ``"boundary"`` / ``"negative"`` / ``"exploratory"``),
            ``requirement_id``, ``title``, ``steps`` (list of step
            strings), and ``priority``.
        coverage_estimate: Predicted ratio of requirement coverage
            achieved by the generated tests, in ``[0.0, 1.0]``.
    """

    model_config = ConfigDict(extra="forbid")

    tests: list[dict[str, Any]] = Field(default_factory=list)
    coverage_estimate: float = 0.0


class TestDataOutput(BaseModel):
    """Output of the Test Data Agent.

    Attributes:
        items: The generated records. Each entry conforms to the
            caller's schema (see
            :class:`~agents.intelligence.test_data.TestDataInput`).
        privacy_safe: ``True`` iff the post-generation validator
            confirmed that no real-looking PII (email, SSN, phone)
            is present. The validator is heuristic; production
            deployments should layer Presidio on top for stronger
            guarantees.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[dict[str, Any]] = Field(default_factory=list)
    privacy_safe: bool = True


class CoverageReport(BaseModel):
    """Output of the Coverage Analysis Agent.

    Attributes:
        requirements_covered: Number of requirements with at least
            one referencing test.
        requirements_total: Total number of requirements analysed.
        tests_total: Total number of tests in scope.
        code_coverage_pct: Authoritative code-coverage percentage
            (``0..100``), typically produced by coverage.py /
            Istanbul / JaCoCo.
        gaps: Human-readable enumeration of missing-coverage
            reasons — suitable for inclusion in the Reporting
            agent's Markdown output.
    """

    model_config = ConfigDict(extra="forbid")

    requirements_covered: int = 0
    requirements_total: int = 0
    tests_total: int = 0
    code_coverage_pct: float = 0.0
    gaps: list[str] = Field(default_factory=list)


class CritiqueRecord(BaseModel):
    """Output of the Critic Agent.

    Attributes:
        target: Identifier of the agent whose output was critiqued.
        passed: ``True`` iff no issues were found.
        issues: Machine-readable list of problems discovered. Each
            entry is a short description.
        suggestions: Human-readable remediation hints.
    """

    model_config = ConfigDict(extra="forbid")

    target: str
    passed: bool
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
