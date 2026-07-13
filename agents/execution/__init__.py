"""Execution agents: Environment, Design Intelligence, Execution, Self-Healing, Failure Analysis, and v2 expansion.

The Execution agents are the platform's **execution layer**. They do the
actual work: spin up environments, run tests, heal broken selectors,
classify failures, and (in v2) measure performance, accessibility,
visual regression, and security.

Module map:

* :mod:`agents.execution.environment` — provision an environment.
* :mod:`agents.execution.design_intel` — DOM → UI semantic graph.
* :mod:`agents.execution.execution` — run structured test specs.
* :mod:`agents.execution.self_healing` — repair failed selectors.
* :mod:`agents.execution.failure_analysis` — classify failures.
* :mod:`agents.execution.visual_regression` — pixel diff vs baseline.
* :mod:`agents.execution.accessibility` — WCAG checks.
* :mod:`agents.execution.performance` — load/stress testing.
* :mod:`agents.execution.security` — SAST/secret/dependency/DAST.
* :mod:`agents.execution.cost_optimization` — recommendations.
"""

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

__all__ = [
    "AccessibilityAgent",
    "CostOptimizationAgent",
    "DesignIntelAgent",
    "EnvironmentAgent",
    "ExecutionAgent",
    "FailureAnalysisAgent",
    "PerformanceAgent",
    "SecurityAgent",
    "SelfHealingAgent",
    "VisualRegressionAgent",
]
