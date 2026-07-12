"""Shared value objects for Tier 2 agents.

These models are the structured outputs that the Tier 2 agents
produce and the Tier 3/4 agents consume. They are deliberately
simple — flat structures with string severities so callers can
serialise them to JSON without a custom encoder.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RequirementsGraph(BaseModel):
    """Output of the Requirements Intel Agent.

    ``requirements`` is a list of dicts (one per requirement) with
    at minimum ``id``, ``title``, ``priority``, ``acceptance_criteria``.
    ``traceability`` lists edges between requirements that share
    significant vocabulary.
    """

    model_config = ConfigDict(extra="forbid")

    requirements: list[dict[str, Any]] = Field(default_factory=list)
    traceability: list[dict[str, Any]] = Field(default_factory=list)


class CodeImpactGraph(BaseModel):
    """Output of the Code Intel Agent.

    ``affected_files`` are the files that should be re-tested given
    the current changes. ``dependencies`` are ``{from, to, symbol}``
    edges. ``impact_summary`` is a one-line human description.
    """

    model_config = ConfigDict(extra="forbid")

    affected_files: list[str] = Field(default_factory=list)
    dependencies: list[dict[str, Any]] = Field(default_factory=list)
    impact_summary: str = ""


class RiskScore(BaseModel):
    """Output of the Risk Assessment Agent.

    Severity levels: ``"low"`` (<0.25), ``"medium"`` (<0.5),
    ``"high"`` (<0.75), ``"critical"`` (>=0.75). ``factors`` lists
    the per-component inputs that produced the score.
    """

    model_config = ConfigDict(extra="forbid")

    score: float  # 0-1
    priority: str  # low | medium | high | critical
    business_impact: str
    factors: list[str] = Field(default_factory=list)


class TestDesignOutput(BaseModel):
    """Output of the Test Design Agent.

    ``tests`` is a list of dicts (one per test) with at minimum
    ``id``, ``type``, ``requirement_id``, ``title``, ``steps``,
    ``priority``. ``coverage_estimate`` is the predicted ratio of
    requirement coverage achieved by the generated tests.
    """

    model_config = ConfigDict(extra="forbid")

    tests: list[dict[str, Any]] = Field(default_factory=list)
    coverage_estimate: float = 0.0


class TestDataOutput(BaseModel):
    """Output of the Test Data Agent.

    ``items`` is a list of generated records; ``privacy_safe`` is
    ``True`` when the agent verified that no real-looking PII
    slipped through the generator.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[dict[str, Any]] = Field(default_factory=list)
    privacy_safe: bool = True


class CoverageReport(BaseModel):
    """Output of the Coverage Analysis Agent.

    ``code_coverage_pct`` is the latest reported code coverage
    percentage (0..100). ``gaps`` lists missing-coverage reasons
    (untested requirements, unexecuted tests, etc.).
    """

    model_config = ConfigDict(extra="forbid")

    requirements_covered: int = 0
    requirements_total: int = 0
    tests_total: int = 0
    code_coverage_pct: float = 0.0
    gaps: list[str] = Field(default_factory=list)


class CritiqueRecord(BaseModel):
    """Output of the Critic Agent.

    ``passed`` is ``True`` when no issues were found. ``issues``
    and ``suggestions`` are machine- and human-readable lists
    respectively.
    """

    model_config = ConfigDict(extra="forbid")

    target: str
    passed: bool
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
