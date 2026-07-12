"""Tier 3 agents: Environment, Design Intelligence, Execution, Self-Healing, Failure Analysis, and v2 expansion.

The Tier 3 agents are the platform's **execution layer**. They do the
actual work: spin up environments, run tests, heal broken selectors,
classify failures, and (in v2) measure performance, accessibility,
visual regression, and security.

Module map:

* :mod:`agents.tier3.environment` — provision an environment.
* :mod:`agents.tier3.design_intel` — DOM → UI semantic graph.
* :mod:`agents.tier3.execution` — run structured test specs.
* :mod:`agents.tier3.self_healing` — repair failed selectors.
* :mod:`agents.tier3.failure_analysis` — classify failures.
* :mod:`agents.tier3.visual_regression` — pixel diff vs baseline.
* :mod:`agents.tier3.accessibility` — WCAG checks.
* :mod:`agents.tier3.performance` — load/stress testing.
* :mod:`agents.tier3.security` — SAST/secret/dependency/DAST.
* :mod:`agents.tier3.cost_optimization` — recommendations.
"""

from agents.tier3.accessibility import AccessibilityAgent
from agents.tier3.cost_optimization import CostOptimizationAgent
from agents.tier3.design_intel import DesignIntelAgent
from agents.tier3.environment import EnvironmentAgent
from agents.tier3.execution import ExecutionAgent
from agents.tier3.failure_analysis import FailureAnalysisAgent
from agents.tier3.performance import PerformanceAgent
from agents.tier3.security import SecurityAgent
from agents.tier3.self_healing import SelfHealingAgent
from agents.tier3.visual_regression import VisualRegressionAgent

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
