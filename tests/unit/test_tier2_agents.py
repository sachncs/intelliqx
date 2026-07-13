"""Tests for Tier 2 Risk Assessment, Test Design, Test Data, Coverage, Critic."""

import pytest
from intelliqx_compute.runtime import InvocationRequest

from agents import register_all
from agents.intelligence.coverage_analysis import CoverageAnalysisAgent
from agents.intelligence.critic import CriticAgent
from agents.intelligence.risk_assessment import RiskAssessmentAgent
from agents.intelligence.test_data import TestDataAgent
from agents.intelligence.test_design import TestDesignAgent

# --- Risk Assessment ---------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_risk_low_when_no_inputs():
    agent = RiskAssessmentAgent()
    out = await agent.invoke(
        InvocationRequest(agent_name="risk_assessment", input={}, tenant_id="t1")
    )
    assert out["score"]["priority"] in {"low", "medium"}
    assert 0 <= out["score"]["score"] <= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_risk_critical_for_many_high_priority_requirements():
    agent = RiskAssessmentAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="risk_assessment",
            input={
                "requirements": [{"priority": "critical"} for _ in range(20)],
                "affected_files": [f"f{i}.py" for i in range(50)],
                "historical_defects": [{} for _ in range(20)],
            },
            tenant_id="t1",
        )
    )
    assert out["score"]["priority"] == "critical"
    assert out["score"]["score"] >= 0.75


@pytest.mark.unit
@pytest.mark.asyncio
async def test_risk_low_for_minimal_change():
    agent = RiskAssessmentAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="risk_assessment",
            input={
                "requirements": [{"priority": "low"}],
                "affected_files": ["f.py"],
                "historical_defects": [],
            },
            tenant_id="t1",
        )
    )
    assert out["score"]["priority"] in {"low", "medium"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_risk_factors_reported():
    agent = RiskAssessmentAgent()
    out = await agent.invoke(
        InvocationRequest(agent_name="risk_assessment", input={}, tenant_id="t1")
    )
    assert len(out["score"]["factors"]) >= 3


# --- Test Design -------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_test_design_generates_three_per_requirement():
    agent = TestDesignAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="test_design",
            input={
                "requirements": [
                    {"id": f"r{i}", "title": f"req {i}", "priority": "medium"} for i in range(5)
                ],
                "tenant_id": "t1",
            },
            tenant_id="t1",
        )
    )
    assert len(out["output"]["tests"]) == 15  # 5 reqs * 3 tests


@pytest.mark.unit
@pytest.mark.asyncio
async def test_test_design_includes_exploratory_for_high_priority():
    agent = TestDesignAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="test_design",
            input={
                "requirements": [{"id": "r1", "title": "req", "priority": "high"}],
                "tenant_id": "t1",
                "min_tests_per_requirement": 4,
            },
            tenant_id="t1",
        )
    )
    types = {t["type"] for t in out["output"]["tests"]}
    assert "exploratory" in types


@pytest.mark.unit
@pytest.mark.asyncio
async def test_test_design_coverage_estimate():
    agent = TestDesignAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="test_design",
            input={
                "requirements": [{"id": "r1", "title": "r", "priority": "low"}],
                "tenant_id": "t1",
                "min_tests_per_requirement": 3,
            },
            tenant_id="t1",
        )
    )
    # 3 tests generated for 1 req, min=3 → coverage = 1.0
    assert out["output"]["coverage_estimate"] == 1.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_test_design_priority_inherited():
    agent = TestDesignAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="test_design",
            input={
                "requirements": [{"id": "r1", "title": "r", "priority": "high"}],
                "tenant_id": "t1",
            },
            tenant_id="t1",
        )
    )
    assert all(t["priority"] == "high" for t in out["output"]["tests"])


# --- Test Data ---------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_test_data_generates_n_rows():
    agent = TestDataAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="test_data",
            input={"schema": {"name": "string", "age": "int"}, "count": 25},
            tenant_id="t1",
        )
    )
    assert len(out["output"]["items"]) == 25


@pytest.mark.unit
@pytest.mark.asyncio
async def test_test_data_email_is_privacy_safe():
    agent = TestDataAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="test_data",
            input={"schema": {"email": "string"}, "count": 5, "privacy_safe": True},
            tenant_id="t1",
        )
    )
    for item in out["output"]["items"]:
        assert item["email"].endswith("@example.com")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_test_data_int_age_in_range():
    agent = TestDataAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="test_data",
            input={"schema": {"age": "int"}, "count": 30},
            tenant_id="t1",
        )
    )
    for item in out["output"]["items"]:
        assert 18 <= item["age"] < 68  # 18 + (idx % 50)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_test_data_privacy_safe_flag():
    agent = TestDataAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="test_data",
            input={"schema": {"email": "string"}, "count": 3, "privacy_safe": True},
            tenant_id="t1",
        )
    )
    assert out["output"]["privacy_safe"] is True


# --- Coverage Analysis --------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_coverage_counts_covered_requirements():
    agent = CoverageAnalysisAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="coverage_analysis",
            input={
                "requirements": [{"id": f"r{i}", "title": f"r{i}"} for i in range(5)],
                "tests": [
                    {"id": "t1", "requirement_id": "r0"},
                    {"id": "t2", "requirement_id": "r1"},
                    {"id": "t3", "requirement_id": "r2"},
                ],
                "executed_tests": [],
                "code_coverage_pct": 0.0,
            },
            tenant_id="t1",
        )
    )
    rep = out["report"]
    assert rep["requirements_covered"] == 3
    assert rep["requirements_total"] == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_coverage_reports_gap_for_untested_requirement():
    agent = CoverageAnalysisAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="coverage_analysis",
            input={
                "requirements": [{"id": "r1", "title": "login"}, {"id": "r2", "title": "logout"}],
                "tests": [{"id": "t1", "requirement_id": "r1"}],
                "executed_tests": [{"test_id": "t1"}],
                "code_coverage_pct": 0.0,
            },
            tenant_id="t1",
        )
    )
    assert any("logout" in g for g in out["report"]["gaps"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_coverage_reports_unexecuted_test():
    agent = CoverageAnalysisAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="coverage_analysis",
            input={
                "requirements": [{"id": "r1", "title": "login"}],
                "tests": [{"id": "t1", "title": "test 1", "requirement_id": "r1"}],
                "executed_tests": [],
                "code_coverage_pct": 0.0,
            },
            tenant_id="t1",
        )
    )
    assert any("not executed" in g for g in out["report"]["gaps"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_coverage_no_gaps_when_full():
    agent = CoverageAnalysisAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="coverage_analysis",
            input={
                "requirements": [{"id": "r1", "title": "login"}],
                "tests": [{"id": "t1", "requirement_id": "r1"}],
                "executed_tests": [{"test_id": "t1"}],
                "code_coverage_pct": 100.0,
            },
            tenant_id="t1",
        )
    )
    assert out["report"]["gaps"] == []


# --- Critic -------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_critic_passes_valid_output():
    agent = CriticAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="critic",
            input={
                "target": "test",
                "output": {"score": 0.5, "priority": "medium"},
                "expected_keys": ["score", "priority"],
            },
            tenant_id="t1",
        )
    )
    assert out["critique"]["passed"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_critic_fails_missing_key():
    agent = CriticAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="critic",
            input={
                "target": "test",
                "output": {"score": 0.5},
                "expected_keys": ["score", "priority"],
            },
            tenant_id="t1",
        )
    )
    assert not out["critique"]["passed"]
    assert any("priority" in i for i in out["critique"]["issues"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_critic_detects_hallucination_marker():
    agent = CriticAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="critic",
            input={
                "target": "test",
                "output": {"result": "[fake:abc123]"},
            },
            tenant_id="t1",
        )
    )
    assert not out["critique"]["passed"]
    assert any("hallucination" in i.lower() for i in out["critique"]["issues"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_critic_rule_non_empty():
    agent = CriticAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="critic",
            input={
                "target": "test",
                "output": {"name": ""},
                "rules": ["non_empty:name"],
            },
            tenant_id="t1",
        )
    )
    assert not out["critique"]["passed"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_critic_rule_type():
    agent = CriticAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="critic",
            input={
                "target": "test",
                "output": {"score": "string-not-int"},
                "rules": ["type:score=int"],
            },
            tenant_id="t1",
        )
    )
    assert not out["critique"]["passed"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_critic_empty_output_fails():
    agent = CriticAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="critic",
            input={"target": "test", "output": {}},
            tenant_id="t1",
        )
    )
    assert not out["critique"]["passed"]


# --- All Tier 2 registered ---------------------------------------------------


@pytest.mark.unit
def test_tier2_agents_registered():
    register_all()
    from intelliqx_agents.registry import get_agent_registry

    reg = get_agent_registry()
    for name in [
        "requirements_intel",
        "code_intel",
        "risk_assessment",
        "test_design",
        "test_data",
        "coverage_analysis",
        "critic",
    ]:
        assert name in reg.list()
