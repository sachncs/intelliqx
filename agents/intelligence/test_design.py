"""Test Design Agent (Tier 2).

Generates structured test specs from a list of requirements. The
default template produces three test types per requirement:

* **Functional** — happy path.
* **Boundary** — edge inputs.
* **Negative** — invalid input handling.

If ``min_tests_per_requirement >= 4`` and a requirement is ``"high"``
or ``"critical"``, a fourth **exploratory** test is added.

The output is a list of test dicts suitable for direct ingestion by
the Tier 3 Execution Agent, which translates each dict into a
sequence of HTTP ``GET`` / ``POST`` / ``assert_status`` /
``assert_json`` steps.

The agent is deterministic and dependency-free; it does not call
any LLM. Coverage is estimated as
``len(tests) / (len(requirements) * min_tests_per_requirement)``,
capped at 1.0.
"""

from __future__ import annotations

from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.ids import new_id
from pydantic import BaseModel, ConfigDict, Field

from agents.intelligence.models import TestDesignOutput


class TestDesignInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[dict[str, Any]] = Field(default_factory=list)
    risk_priority: str = "medium"
    tenant_id: str
    min_tests_per_requirement: int = 3


class TestDesignAgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: TestDesignOutput


class TestDesignAgent(AgentBase):
    META = AgentMeta(
        name="test_design",
        tier=2,
        version="0.1.0",
        description="Generates functional, boundary, negative tests from requirements.",
    )
    INPUT_MODEL = TestDesignInput
    OUTPUT_MODEL = TestDesignAgentOutput

    @traced_agent("test_design")
    async def run(self, ctx: AgentContext, input: TestDesignInput) -> TestDesignAgentOutput:
        tests: list[dict[str, Any]] = []
        for req in input.requirements:
            title = req.get("title", "")
            req_id = req.get("id", f"req-{new_id()}")
            # Functional
            tests.append(
                {
                    "id": f"test-{new_id()}",
                    "type": "functional",
                    "requirement_id": req_id,
                    "title": f"Verify {title}",
                    "steps": [
                        f"Given precondition for {title}",
                        f"When user invokes {title}",
                        f"Then the system handles {title}",
                    ],
                    "priority": req.get("priority", input.risk_priority),
                }
            )
            # Boundary
            tests.append(
                {
                    "id": f"test-{new_id()}",
                    "type": "boundary",
                    "requirement_id": req_id,
                    "title": f"Boundary condition for {title}",
                    "steps": [
                        "Given edge input values",
                        "When the operation is performed",
                        "Then the system handles boundaries",
                    ],
                    "priority": req.get("priority", input.risk_priority),
                }
            )
            # Negative
            tests.append(
                {
                    "id": f"test-{new_id()}",
                    "type": "negative",
                    "requirement_id": req_id,
                    "title": f"Invalid input for {title}",
                    "steps": [
                        "Given invalid input",
                        "When the operation is performed",
                        "Then the system rejects with error",
                    ],
                    "priority": req.get("priority", input.risk_priority),
                }
            )
            # Optional exploratory test for high-priority requirements
            # when the caller asked for at least four tests per
            # requirement.
            if input.min_tests_per_requirement >= 4 and req.get("priority") in {
                "high",
                "critical",
            }:
                tests.append(
                    {
                        "id": f"test-{new_id()}",
                        "type": "exploratory",
                        "requirement_id": req_id,
                        "title": f"Exploratory scenarios for {title}",
                        "steps": [
                            "Explore permutations",
                            "Document unexpected behaviors",
                        ],
                        "priority": req.get("priority", input.risk_priority),
                    }
                )
        # Coverage estimate: actual tests divided by the target
        # (requirements x per-requirement minimum). Capped at 1.0.
        coverage = min(
            1.0, len(tests) / max(1, len(input.requirements) * input.min_tests_per_requirement)
        )
        return TestDesignAgentOutput(
            output=TestDesignOutput(tests=tests, coverage_estimate=coverage)
        )
