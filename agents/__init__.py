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

from intelliqx_agents.registry import get_agent_registry


def register_all() -> None:
    """Register every Tier 1-4 agent with the AgentRegistry."""
    from agents.coordination.knowledge_rag import KnowledgeRAGAgent
    from agents.coordination.memory_manager import MemoryManagerAgent
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

    reg = get_agent_registry()
    reg.register("planner", lambda: PlannerAgent(), meta=PlannerAgent.META)
    reg.register("orchestrator", lambda: OrchestratorAgent(), meta=OrchestratorAgent.META)
    reg.register("memory_manager", lambda: MemoryManagerAgent(), meta=MemoryManagerAgent.META)
    reg.register("knowledge_rag", lambda: KnowledgeRAGAgent(), meta=KnowledgeRAGAgent.META)
    reg.register("tool_manager", lambda: ToolManagerAgent(), meta=ToolManagerAgent.META)
    reg.register("smoke", lambda: SmokeAgent(), meta=SmokeAgent.META)

    reg.register(
        "requirements_intel", lambda: RequirementsIntelAgent(), meta=RequirementsIntelAgent.META
    )
    reg.register("code_intel", lambda: CodeIntelAgent(), meta=CodeIntelAgent.META)
    reg.register("risk_assessment", lambda: RiskAssessmentAgent(), meta=RiskAssessmentAgent.META)
    reg.register("test_design", lambda: TestDesignAgent(), meta=TestDesignAgent.META)
    reg.register("test_data", lambda: TestDataAgent(), meta=TestDataAgent.META)
    reg.register(
        "coverage_analysis", lambda: CoverageAnalysisAgent(), meta=CoverageAnalysisAgent.META
    )
    reg.register("critic", lambda: CriticAgent(), meta=CriticAgent.META)
    reg.register("learning", lambda: LearningAgent(), meta=LearningAgent.META)
    reg.register(
        "prompt_management", lambda: PromptManagementAgent(), meta=PromptManagementAgent.META
    )

    reg.register("environment", lambda: EnvironmentAgent(), meta=EnvironmentAgent.META)
    reg.register("design_intel", lambda: DesignIntelAgent(), meta=DesignIntelAgent.META)
    reg.register("execution", lambda: ExecutionAgent(), meta=ExecutionAgent.META)
    reg.register("self_healing", lambda: SelfHealingAgent(), meta=SelfHealingAgent.META)
    reg.register("failure_analysis", lambda: FailureAnalysisAgent(), meta=FailureAnalysisAgent.META)
    reg.register(
        "visual_regression", lambda: VisualRegressionAgent(), meta=VisualRegressionAgent.META
    )
    reg.register("accessibility", lambda: AccessibilityAgent(), meta=AccessibilityAgent.META)
    reg.register("performance", lambda: PerformanceAgent(), meta=PerformanceAgent.META)
    reg.register("security", lambda: SecurityAgent(), meta=SecurityAgent.META)
    reg.register(
        "cost_optimization", lambda: CostOptimizationAgent(), meta=CostOptimizationAgent.META
    )

    reg.register("observability", lambda: ObservabilityAgent(), meta=ObservabilityAgent.META)
    reg.register("reporting", lambda: ReportingAgent(), meta=ReportingAgent.META)
    reg.register(
        "governance_compliance",
        lambda: GovernanceComplianceAgent(),
        meta=GovernanceComplianceAgent.META,
    )
    reg.register(
        "release_readiness", lambda: ReleaseReadinessAgent(), meta=ReleaseReadinessAgent.META
    )


def register_compute_handlers() -> None:
    """Register every agent's ``run`` method with the in-process compute runtime.

    The handler closure captures the agent instance so each
    invocation produces a fresh :class:`intelliqx_compute.runtime.InvocationResponse`.
    """
    from intelliqx_compute.runtime import get_compute_runtime

    from agents.coordination.knowledge_rag import KnowledgeRAGAgent
    from agents.coordination.memory_manager import MemoryManagerAgent
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

    runtime = get_compute_runtime()
    for name, cls in [
        ("planner", PlannerAgent),
        ("orchestrator", OrchestratorAgent),
        ("memory_manager", MemoryManagerAgent),
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
    ]:
        instance = cls()

        async def handler(req, _instance=instance):
            return await _instance.invoke(req)

        runtime.register(name, handler)
