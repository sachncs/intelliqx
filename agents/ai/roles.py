"""Single Pydantic AI :class:`Agent` factory per IntelliqX role.

The :func:`build` function returns a list of :class:`AgentRole`
records. The :class:`RoleSpec` dataclass captures everything needed
for a single role; the catalog at the bottom of the file drives the
table. ``build_runtime`` is the only construction point.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from intelliqx_ai.runtime import AgentConfig, build_agent
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class RoleSpec:
    """One row of the role table.

    Attributes:
        name: Unique registry key.
        category: Coordination, intelligence, execution, or governance.
        instructions: System prompt for the model.
        output_model: Optional structured Pydantic model; when ``None``
            the role returns a plain string.
    """

    name: str
    category: str
    instructions: str
    output_model: type[BaseModel] | None = None


def _hit() -> type[BaseModel]:
    """Single-hit record used by retrieval-style roles."""

    class Hit(BaseModel):
        id: str
        text: str

    return Hit


def _retrieval_result() -> type[BaseModel]:
    """Wrapper holding a list of hits; required because Pydantic AI needs
    a single model object as ``output_type``.
    """

    class RetrievalResult(BaseModel):
        hits: list[_hit()]  # type: ignore[valid-type]

    return RetrievalResult


def _items_result(model: type[BaseModel]) -> type[BaseModel]:
    """Wrap a single item model in an ``items`` list."""

    class ItemsResult(BaseModel):
        items: list[model]  # type: ignore[valid-type]

    return ItemsResult


def _execution_result() -> type[BaseModel]:
    class ExecutionResult(BaseModel):
        passed: int = 0
        failed: int = 0
        outcome: str = "passed"

    return ExecutionResult


def _self_healing_plan() -> type[BaseModel]:
    class SelfHealingPlan(BaseModel):
        selector: str
        confidence: float = 0.0

    return SelfHealingPlan


def _decision() -> type[BaseModel]:
    class ReleaseDecision(BaseModel):
        recommendation: str
        confidence: float
        outcome: str

    return ReleaseDecision


def _plan() -> type[BaseModel]:
    class PlanResult(BaseModel):
        goal_id: str
        steps: list[str] = Field(default_factory=list)

    return PlanResult


def _done() -> type[BaseModel]:
    class Done(BaseModel):
        ok: bool = True

    return Done


def _impact() -> type[BaseModel]:
    class Impact(BaseModel):
        files: list[str] = Field(default_factory=list)

    return Impact


def _risk() -> type[BaseModel]:
    class Risk(BaseModel):
        score: float
        rationale: str

    return Risk


def _case() -> type[BaseModel]:
    class TestCase(BaseModel):
        name: str
        steps: list[str] = Field(default_factory=list)

    return TestCase


def _coverage() -> type[BaseModel]:
    class Coverage(BaseModel):
        percent: float
        gaps: list[str] = Field(default_factory=list)

    return Coverage


def _critique() -> type[BaseModel]:
    class Critique(BaseModel):
        issues: list[str] = Field(default_factory=list)

    return Critique


def _requirement() -> type[BaseModel]:
    class Requirement(BaseModel):
        id: str
        text: str

    return Requirement


def _requirement_list() -> type[BaseModel]:
    class RequirementList(BaseModel):
        items: list[_requirement()]  # type: ignore[valid-type]

    return RequirementList


def _test_case_list() -> type[BaseModel]:
    class TestCaseList(BaseModel):
        cases: list[_case()]  # type: ignore[valid-type]

    return TestCaseList


_CATEGORIES = frozenset({"coordination", "intelligence", "execution", "governance"})

ROLE_TABLE: tuple[RoleSpec, ...] = (
    RoleSpec(
        name="planner",
        category="coordination",
        instructions=(
            "You are the IntelliqX planner. Given a goal, produce a "
            "deterministic step-by-step plan using only the named agents."
        ),
        output_model=_plan(),
    ),
    RoleSpec(
        name="orchestrator",
        category="coordination",
        instructions=("IntelliqX orchestrator. Always emit one terminal result."),
        output_model=_done(),
    ),
    RoleSpec(
        name="knowledge_rag",
        category="coordination",
        instructions=(
            "Return the best matching knowledge snippets as a JSON " "{hits: [{id, text}]} object."
        ),
        output_model=_retrieval_result(),
    ),
    RoleSpec(
        name="tool_manager",
        category="coordination",
        instructions="Return the tool execution result.",
    ),
    RoleSpec(
        name="smoke",
        category="coordination",
        instructions="Echo the input and return one short string.",
    ),
    RoleSpec(
        name="requirements_intel",
        category="intelligence",
        instructions=("Extract requirements as a JSON {items: [{id, text}]} object."),
        output_model=_requirement_list(),
    ),
    RoleSpec(
        name="code_intel",
        category="intelligence",
        instructions="Return the list of files affected by the change.",
        output_model=_impact(),
    ),
    RoleSpec(
        name="risk_assessment",
        category="intelligence",
        instructions="Score the proposed change 0..1 and explain in one sentence.",
        output_model=_risk(),
    ),
    RoleSpec(
        name="test_design",
        category="intelligence",
        instructions="Return test cases as a JSON {cases: [{name, steps:[...]}]} object.",
        output_model=_test_case_list(),
    ),
    RoleSpec(
        name="test_data",
        category="intelligence",
        instructions="Return a JSON dataset string for the test plan.",
    ),
    RoleSpec(
        name="coverage_analysis",
        category="intelligence",
        instructions="Return coverage percent 0..100 and the list of gap names.",
        output_model=_coverage(),
    ),
    RoleSpec(
        name="critic",
        category="intelligence",
        instructions="List every schema violation or hallucination in the input.",
        output_model=_critique(),
    ),
    RoleSpec(
        name="learning",
        category="intelligence",
        instructions="Persist feedback and return one short summary.",
    ),
    RoleSpec(
        name="prompt_management",
        category="intelligence",
        instructions="Return the selected prompt version id.",
    ),
    RoleSpec(
        name="environment",
        category="execution",
        instructions="Start the system under test and return the base URL.",
    ),
    RoleSpec(
        name="design_intel",
        category="execution",
        instructions="Return a concise DOM snapshot of the running page.",
    ),
    RoleSpec(
        name="execution",
        category="execution",
        instructions="Run the test plan and return {passed, failed, outcome}.",
        output_model=_execution_result(),
    ),
    RoleSpec(
        name="self_healing",
        category="execution",
        instructions="Return the recovered selector and a 0..1 confidence score.",
        output_model=_self_healing_plan(),
    ),
    RoleSpec(
        name="failure_analysis",
        category="execution",
        instructions="Return a one-line failure category.",
    ),
    RoleSpec(
        name="visual_regression", category="execution", instructions="Return 'match' or 'mismatch'."
    ),
    RoleSpec(
        name="accessibility",
        category="execution",
        instructions="Return the list of WCAG issues as JSON.",
    ),
    RoleSpec(
        name="performance",
        category="execution",
        instructions="Return p50/p95/p99 latencies as JSON.",
    ),
    RoleSpec(
        name="security",
        category="execution",
        instructions="Return the list of security findings as JSON.",
    ),
    RoleSpec(
        name="cost_optimization",
        category="execution",
        instructions="Return the recommended cost-saving changes as JSON.",
    ),
    RoleSpec(
        name="observability", category="governance", instructions="Return the SLO summary as JSON."
    ),
    RoleSpec(
        name="reporting", category="governance", instructions="Return the markdown run report."
    ),
    RoleSpec(
        name="governance_compliance",
        category="governance",
        instructions="Return the approval decision and audit record ids.",
    ),
    RoleSpec(
        name="release_readiness",
        category="governance",
        instructions="Return {recommendation, confidence, outcome}.",
        output_model=_decision(),
    ),
)


def build_agent_for_role(spec: RoleSpec, *, agent_config: AgentConfig | None = None) -> Any:
    """Construct a fresh Pydantic AI :class:`Agent` for ``spec``."""
    return build_agent(
        name=spec.name,
        output_type=spec.output_model or str,
        instructions=spec.instructions,
        agent_config=agent_config,
    )


@dataclass(frozen=True)
class AgentRole:
    """A registered agent role.

    Attributes:
        name: Unique registry key.
        category: Coordination, intelligence, execution, or governance.
        description: One-line summary used for marketplace listings.
        output_type: The Pydantic model returned by the model, or
            :class:`str` for free-form output.
        factory: Zero-arg factory that returns a fully-configured
            Pydantic AI :class:`Agent`.
    """

    name: str
    category: str
    description: str
    output_type: Any
    factory: Callable[[], Any] = field(default=lambda: None)


def build_roles() -> list[AgentRole]:
    """Return every role in :data:`ROLE_TABLE` as an :class:`AgentRole`."""
    roles: list[AgentRole] = []
    for spec in ROLE_TABLE:
        if spec.category not in _CATEGORIES:
            raise ValueError(f"Unknown role category: {spec.category!r}")
        description = spec.instructions
        roles.append(
            AgentRole(
                name=spec.name,
                category=spec.category,
                description=description,
                output_type=spec.output_model or str,
                factory=_build_factory(spec),
            )
        )
    return roles


def _build_factory(spec: RoleSpec) -> Any:
    """Return a zero-arg callable that produces the role's Pydantic AI :class:`Agent`."""
    return lambda: build_agent_for_role(spec)


__all__ = ["ROLE_TABLE", "AgentRole", "RoleSpec", "build_agent_for_role", "build_roles"]
