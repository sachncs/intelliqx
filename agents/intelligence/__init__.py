"""Tier 2 agents: domain intelligence and reasoning.

These agents are the platform's "thinking" layer. They consume
requirements, source code, test designs, and historical data to
produce structured outputs that the Tier 3 execution agents consume.

Module map:

* :mod:`agents.intelligence.requirements_intel` — PRD → structured requirements.
* :mod:`agents.intelligence.code_intel` — files → impact + dependency graphs.
* :mod:`agents.intelligence.risk_assessment` — composite risk score.
* :mod:`agents.intelligence.test_design` — requirements → test specs.
* :mod:`agents.intelligence.test_data` — schema → synthetic dataset.
* :mod:`agents.intelligence.coverage_analysis` — requirements + tests + exec
  → coverage report.
* :mod:`agents.intelligence.critic` — validates any other agent's output.
* :mod:`agents.intelligence.learning` — runs A/B feedback loop.
* :mod:`agents.intelligence.prompt_management` — versioned prompts + bandit.
"""

from agents.intelligence.code_intel import CodeIntelAgent
from agents.intelligence.coverage_analysis import CoverageAnalysisAgent
from agents.intelligence.critic import CriticAgent
from agents.intelligence.learning import LearningAgent
from agents.intelligence.prompt_management import PromptManagementAgent
from agents.intelligence.requirements_intel import RequirementsIntelAgent
from agents.intelligence.risk_assessment import RiskAssessmentAgent
from agents.intelligence.test_data import TestDataAgent
from agents.intelligence.test_design import TestDesignAgent

__all__ = [
    "CodeIntelAgent",
    "CoverageAnalysisAgent",
    "CriticAgent",
    "LearningAgent",
    "PromptManagementAgent",
    "RequirementsIntelAgent",
    "RiskAssessmentAgent",
    "TestDataAgent",
    "TestDesignAgent",
]
