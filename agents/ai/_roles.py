"""Build the Pydantic AI :class:`Agent` for every IntelliqX role.

The builder is a single file. Each role is one tiny factory. The
existing pure-Python algorithms are exposed as Pydantic AI tools or
output functions so callers do not need to learn a new framework
beyond the shared :class:`intelliqx_ai.runtime.build_runtime`.
"""

from __future__ import annotations

from typing import Any

from intelliqx_ai.runtime import build_runtime
from pydantic import BaseModel, Field


def _output(name: str) -> type[BaseModel]:
    """Create a minimal output schema with one ``result: str`` field."""
    return type(
        name,
        (BaseModel,),
        {
            "__annotations__": {"result": str},
            "model_config": __import__("pydantic").ConfigDict(extra="forbid"),
        },
    )


def planner() -> Any:
    from pydantic import BaseModel, Field

    class PlanResult(BaseModel):
        goal_id: str
        steps: list[str] = Field(default_factory=list)

    return build_runtime(
        name="planner",
        output_type=PlanResult,
        instructions=(
            "You are the IntelliqX planner. Given a goal, produce a "
            "deterministic step-by-step plan using only the named "
            "agents."
        ),
    )


def orchestrator() -> Any:
    class _Done(BaseModel):
        ok: bool = True

    return build_runtime(
        name="orchestrator",
        output_type=_Done,
        instructions="IntelliqX orchestrator. Always emit one terminal result.",
    )


def knowledge_rag() -> Any:
    class Hit(BaseModel):
        id: str
        text: str

    class Result(BaseModel):
        hits: list[Hit]

    return build_runtime(
        name="knowledge_rag",
        output_type=Result,
        instructions=(
            "Return the best matching knowledge snippets as a JSON " "{hits: [{id, text}]} object."
        ),
    )


def tool_manager() -> Any:
    return build_runtime(
        name="tool_manager", output_type=str, instructions="Return the tool execution result."
    )


def smoke() -> Any:
    return build_runtime(
        name="smoke", output_type=str, instructions="Echo the input and return one short string."
    )


def requirements_intel() -> Any:
    class Requirement(BaseModel):
        id: str
        text: str

    class Result(BaseModel):
        items: list[Requirement]

    return build_runtime(
        name="requirements_intel",
        output_type=Result,
        instructions="Extract requirements as a JSON {items: [{id, text}]} object.",
    )


def code_intel() -> Any:
    class _Impact(BaseModel):
        files: list[str] = Field(default_factory=list)

    return build_runtime(
        name="code_intel",
        output_type=_Impact,
        instructions="Return the list of files affected by the change.",
    )


def risk_assessment() -> Any:
    class _Risk(BaseModel):
        score: float
        rationale: str

    return build_runtime(
        name="risk_assessment",
        output_type=_Risk,
        instructions="Score the proposed change 0..1 and explain in one sentence.",
    )


def test_design() -> Any:
    class _Case(BaseModel):
        name: str
        steps: list[str] = Field(default_factory=list)

    class _Result(BaseModel):
        cases: list[_Case]

    return build_runtime(
        name="test_design",
        output_type=_Result,
        instructions="Return test cases as a JSON {cases: [{name, steps:[...]}]} object.",
    )


def test_data() -> Any:
    return build_runtime(
        name="test_data",
        output_type=str,
        instructions="Return a JSON dataset string for the test plan.",
    )


def coverage_analysis() -> Any:
    class _Coverage(BaseModel):
        percent: float
        gaps: list[str] = Field(default_factory=list)

    return build_runtime(
        name="coverage_analysis",
        output_type=_Coverage,
        instructions="Return coverage percent 0..100 and the list of gap names.",
    )


def critic() -> Any:
    class _Critique(BaseModel):
        issues: list[str] = Field(default_factory=list)

    return build_runtime(
        name="critic",
        output_type=_Critique,
        instructions="List every schema violation or hallucination in the input.",
    )


def learning() -> Any:
    return build_runtime(
        name="learning",
        output_type=str,
        instructions="Persist feedback and return one short summary.",
    )


def prompt_management() -> Any:
    return build_runtime(
        name="prompt_management",
        output_type=str,
        instructions="Return the selected prompt version id.",
    )


def environment() -> Any:
    return build_runtime(
        name="environment",
        output_type=str,
        instructions="Start the system under test and return the base URL.",
    )


def design_intel() -> Any:
    return build_runtime(
        name="design_intel",
        output_type=str,
        instructions="Return a concise DOM snapshot of the running page.",
    )


def execution() -> Any:
    class _Result(BaseModel):
        passed: int = 0
        failed: int = 0
        outcome: str = "passed"

    return build_runtime(
        name="execution",
        output_type=_Result,
        instructions="Run the test plan and return {passed, failed, outcome}.",
    )


def self_healing() -> Any:
    class _Plan(BaseModel):
        selector: str
        confidence: float = 0.0

    return build_runtime(
        name="self_healing",
        output_type=_Plan,
        instructions="Return the recovered selector and a 0..1 confidence score.",
    )


def failure_analysis() -> Any:
    return build_runtime(
        name="failure_analysis", output_type=str, instructions="Return a one-line failure category."
    )


def visual_regression() -> Any:
    return build_runtime(
        name="visual_regression", output_type=str, instructions="Return 'match' or 'mismatch'."
    )


def accessibility() -> Any:
    return build_runtime(
        name="accessibility",
        output_type=str,
        instructions="Return the list of WCAG issues as JSON.",
    )


def performance() -> Any:
    return build_runtime(
        name="performance", output_type=str, instructions="Return p50/p95/p99 latencies as JSON."
    )


def security() -> Any:
    return build_runtime(
        name="security",
        output_type=str,
        instructions="Return the list of security findings as JSON.",
    )


def cost_optimization() -> Any:
    return build_runtime(
        name="cost_optimization",
        output_type=str,
        instructions="Return the recommended cost-saving changes as JSON.",
    )


def observability() -> Any:
    return build_runtime(
        name="observability", output_type=str, instructions="Return the SLO summary as JSON."
    )


def reporting() -> Any:
    return build_runtime(
        name="reporting", output_type=str, instructions="Return the markdown run report."
    )


def governance_compliance() -> Any:
    return build_runtime(
        name="governance_compliance",
        output_type=str,
        instructions="Return the approval decision and audit record ids.",
    )


def release_readiness() -> Any:
    class _Decision(BaseModel):
        recommendation: str
        confidence: float
        outcome: str

    return build_runtime(
        name="release_readiness",
        output_type=_Decision,
        instructions="Return {recommendation, confidence, outcome}.",
    )


def build() -> list[Any]:
    """Return every role in a list of :class:`AgentRole`."""
    from agents import AgentRole

    roles: list[AgentRole] = []
    catalog: list[tuple[str, str, Any]] = [
        ("planner", "coordination", planner),
        ("orchestrator", "coordination", orchestrator),
        ("knowledge_rag", "coordination", knowledge_rag),
        ("tool_manager", "coordination", tool_manager),
        ("smoke", "coordination", smoke),
        ("requirements_intel", "intelligence", requirements_intel),
        ("code_intel", "intelligence", code_intel),
        ("risk_assessment", "intelligence", risk_assessment),
        ("test_design", "intelligence", test_design),
        ("test_data", "intelligence", test_data),
        ("coverage_analysis", "intelligence", coverage_analysis),
        ("critic", "intelligence", critic),
        ("learning", "intelligence", learning),
        ("prompt_management", "intelligence", prompt_management),
        ("environment", "execution", environment),
        ("design_intel", "execution", design_intel),
        ("execution", "execution", execution),
        ("self_healing", "execution", self_healing),
        ("failure_analysis", "execution", failure_analysis),
        ("visual_regression", "execution", visual_regression),
        ("accessibility", "execution", accessibility),
        ("performance", "execution", performance),
        ("security", "execution", security),
        ("cost_optimization", "execution", cost_optimization),
        ("observability", "governance", observability),
        ("reporting", "governance", reporting),
        ("governance_compliance", "governance", governance_compliance),
        ("release_readiness", "governance", release_readiness),
    ]
    for name, category, factory in catalog:
        agent = factory()
        roles.append(
            AgentRole(
                name=name,
                category=category,
                description=agent._instructions,
                builder=factory,
            )
        )
    return roles


__all__ = ["build"]
