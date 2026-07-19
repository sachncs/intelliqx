"""Agent registry bootstrap for IntelliqX.

Imports and registers every agent with the
:class:`intelliqx_agents.registry.AgentRegistry`, and wires each agent's
``run`` method to the :class:`intelliqx_compute.runtime.InProcessComputeRuntime`
so the Orchestrator can dispatch to them by name.

Two entry points:

* :func:`register_all` — adds factories to the agent registry
  (used by the marketplace / health endpoints).
* :func:`register_compute_handlers` — installs the same factories
  into the compute runtime so the Orchestrator can invoke them.

Calling both is idempotent; tests typically call them once in a
conftest fixture.

Phase status:

* Coordination (Planner, Orchestrator, Memory, Knowledge/RAG 4-source,
  Tool Manager, Smoke) — Phase 1.
* Intelligence (Requirements Intel, Code Intel, Risk, Test Design, Test
  Data, Coverage, Critic, Learning, Prompt Management) — Phases 3
  & 6.
* Execution (Environment, Design Intel, Execution, Self-Healing,
  Failure Analysis, Visual Regression, Accessibility, Performance,
  Security, Cost Optimization) — Phases 4 & 6.
* Governance (Observability, Reporting, Governance & Compliance,
  Release Readiness) — Phase 5.
"""

from __future__ import annotations

from typing import Any

from intelliqx_agents.registry import get_agent_registry

AGENT_CATALOG: list[tuple[str, Any]] = []

__all__ = [
    "AGENT_CATALOG",
    "build_catalog",
    "register_all",
    "register_compute_handlers",
]


def build_catalog() -> list[tuple[str, Any]]:
    """Lazily build the name→class mapping (avoids import-time side effects)."""
    if AGENT_CATALOG:
        return AGENT_CATALOG
    from agents.coordination.knowledge_rag import KnowledgeRAGAgent
    from agents.coordination.orchestrator import OrchestratorAgent
    from agents.coordination.planner import PlannerAgent
    from agents.coordination.smoke import SmokeAgent
    from agents.coordination.tool_manager import ToolManagerAgent
    from agents.execution.accessibility import AccessibilityAgent
    from agents.execution.cost_optimization import CostOptimizationAgent
    from agents.execution.design_intel import DesignIntelAgent
    from agents.execution.environment import EnvironmentAgent
    from agents.execution.execution import ExecutionAgent
    from agents.execution.failure_analysis import FailureAnalysisAgent
    from agents.execution.performance import PerformanceAgent
    from agents.execution.security import SecurityAgent
    from agents.execution.self_healing import SelfHealingAgent
    from agents.execution.visual_regression import VisualRegressionAgent
    from agents.governance.governance_compliance import GovernanceComplianceAgent
    from agents.governance.observability import ObservabilityAgent
    from agents.governance.release_readiness import ReleaseReadinessAgent
    from agents.governance.reporting import ReportingAgent
    from agents.intelligence.code_intel import CodeIntelAgent
    from agents.intelligence.coverage_analysis import CoverageAnalysisAgent
    from agents.intelligence.critic import CriticAgent
    from agents.intelligence.learning import LearningAgent
    from agents.intelligence.prompt_management import PromptManagementAgent
    from agents.intelligence.requirements_intel import RequirementsIntelAgent
    from agents.intelligence.risk_assessment import RiskAssessmentAgent
    from agents.intelligence.test_data import TestDataAgent
    from agents.intelligence.test_design import TestDesignAgent

    AGENT_CATALOG.extend([
        ("planner", PlannerAgent),
        ("orchestrator", OrchestratorAgent),
        ("knowledge_rag", KnowledgeRAGAgent),
        ("tool_manager", ToolManagerAgent),
        ("smoke", SmokeAgent),
        ("requirements_intel", RequirementsIntelAgent),
        ("code_intel", CodeIntelAgent),
        ("risk_assessment", RiskAssessmentAgent),
        ("test_design", TestDesignAgent),
        ("test_data", TestDataAgent),
        ("coverage_analysis", CoverageAnalysisAgent),
        ("critic", CriticAgent),
        ("learning", LearningAgent),
        ("prompt_management", PromptManagementAgent),
        ("environment", EnvironmentAgent),
        ("design_intel", DesignIntelAgent),
        ("execution", ExecutionAgent),
        ("self_healing", SelfHealingAgent),
        ("failure_analysis", FailureAnalysisAgent),
        ("visual_regression", VisualRegressionAgent),
        ("accessibility", AccessibilityAgent),
        ("performance", PerformanceAgent),
        ("security", SecurityAgent),
        ("cost_optimization", CostOptimizationAgent),
        ("observability", ObservabilityAgent),
        ("reporting", ReportingAgent),
        ("governance_compliance", GovernanceComplianceAgent),
        ("release_readiness", ReleaseReadinessAgent),
    ])
    return AGENT_CATALOG


def register_all() -> None:
    """Register every agent with the AgentRegistry."""
    catalog = build_catalog()
    reg = get_agent_registry()
    for name, cls in catalog:
        reg.register(name, lambda _cls=cls: _cls(), meta=cls.META)


def register_compute_handlers() -> None:
    """Register every agent's ``run`` method with the in-process compute runtime."""
    from intelliqx_compute.runtime import get_compute_runtime

    catalog = build_catalog()
    runtime = get_compute_runtime()
    for name, cls in catalog:
        instance = cls()

        async def handler(req, _instance=instance):
            return await _instance.invoke(req)

        runtime.register(name, handler)
