"""Tier 2 agents: domain intelligence and reasoning.

These agents are the platform's "thinking" layer. They consume
requirements, source code, test designs, and historical data to
produce structured outputs that the Tier 3 execution agents consume.

Module map:

* :mod:`agents.tier2.requirements_intel` — PRD → structured requirements.
* :mod:`agents.tier2.code_intel` — files → impact + dependency graphs.
* :mod:`agents.tier2.risk_assessment` — composite risk score.
* :mod:`agents.tier2.test_design` — requirements → test specs.
* :mod:`agents.tier2.test_data` — schema → synthetic dataset.
* :mod:`agents.tier2.coverage_analysis` — requirements + tests + exec
  → coverage report.
* :mod:`agents.tier2.critic` — validates any other agent's output.
* :mod:`agents.tier2.learning` — runs A/B feedback loop.
* :mod:`agents.tier2.prompt_management` — versioned prompts + bandit.
"""

from agents.tier2.code_intel import CodeIntelAgent
from agents.tier2.coverage_analysis import CoverageAnalysisAgent
from agents.tier2.critic import CriticAgent
from agents.tier2.learning import LearningAgent
from agents.tier2.prompt_management import PromptManagementAgent
from agents.tier2.requirements_intel import RequirementsIntelAgent
from agents.tier2.risk_assessment import RiskAssessmentAgent
from agents.tier2.test_data import TestDataAgent
from agents.tier2.test_design import TestDesignAgent

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
