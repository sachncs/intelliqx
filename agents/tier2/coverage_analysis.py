"""Coverage Analysis Agent (Tier 2).

Aggregates requirement, test, and code coverage into a single
:class:`CoverageReport`. The agent does not run anything; it just
merges inputs:

* **Requirement coverage** is the fraction of requirements that
  have at least one test referencing them.
* **Test execution coverage** is computed from
  ``input.executed_tests``: a test that was never executed is a
  gap.
* **Code coverage** is taken from the input verbatim (the
  ``code_coverage_pct`` field is set by an external code-coverage
  tool such as coverage.py, Istanbul, or JaCoCo).

The ``gaps`` list is a human-readable enumeration of the missing
items, suitable for inclusion in the Reporting agent's Markdown
output.
"""

from __future__ import annotations

from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from pydantic import BaseModel, ConfigDict, Field

from agents.tier2.models import CoverageReport


class CoverageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[dict[str, Any]] = Field(default_factory=list)
    tests: list[dict[str, Any]] = Field(default_factory=list)
    executed_tests: list[dict[str, Any]] = Field(default_factory=list)
    code_coverage_pct: float = 0.0


class CoverageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: CoverageReport


class CoverageAnalysisAgent(AgentBase):
    META = AgentMeta(
        name="coverage_analysis",
        tier=2,
        version="0.1.0",
        description="Aggregates requirement, test, and code coverage.",
    )
    INPUT_MODEL = CoverageInput
    OUTPUT_MODEL = CoverageOutput

    @traced_agent("coverage_analysis")
    async def run(self, ctx: AgentContext, input: CoverageInput) -> CoverageOutput:
        covered_reqs = {t["requirement_id"] for t in input.tests if "requirement_id" in t}
        all_reqs = {r.get("id") for r in input.requirements if r.get("id")}
        gaps: list[str] = []
        # Untested requirements
        for rid in all_reqs - covered_reqs:
            gap_title = next(
                (r.get("title", rid) for r in input.requirements if r.get("id") == rid),
                rid,
            )
            gaps.append(f"Requirement {gap_title} has no tests")
        # Unexecuted tests
        executed_ids = {e["test_id"] for e in input.executed_tests if "test_id" in e}
        for t in input.tests:
            if t.get("id") not in executed_ids:
                gaps.append(f"Test {t.get('title', t.get('id'))} not executed in latest run")

        report = CoverageReport(
            requirements_covered=len(covered_reqs),
            requirements_total=len(all_reqs),
            tests_total=len(input.tests),
            code_coverage_pct=input.code_coverage_pct,
            gaps=gaps,
        )
        return CoverageOutput(report=report)
