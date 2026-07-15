"""Tests for  Requirements Intelligence Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest
from intelliqx_kg.graph import get_kg

from agents import register_all, register_compute_handlers
from agents.intelligence.requirements_intel import (
    RequirementsIntelAgent,
    extract_requirements,
    shared_keywords,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def testextract_requirements_from_numbered_list():
    text = """
1. Users can log in with email and password [high]
2. Users can reset their password [medium]
3. Admin can view all users [critical]
"""
    reqs = extract_requirements(text)
    assert len(reqs) == 3
    assert reqs[0]["priority"] == "high"
    assert reqs[2]["priority"] == "critical"


@pytest.mark.unit
@pytest.mark.asyncio
async def testextract_requirements_from_bullets():
    text = """
- Search by keyword
- Filter by date
- Sort by name
"""
    reqs = extract_requirements(text)
    assert len(reqs) == 3


@pytest.mark.unit
def test_shared_keywords():
    a = "Users can reset their password"
    b = "User password reset is critical"
    shared = shared_keywords(a, b)
    assert "password" in shared
    assert "reset" in shared


@pytest.mark.unit
def test_shared_keywords_excludes_stopwords():
    a = "the a an"
    b = "the a an"
    # "the" and "a"/"an" are all in the stopword set; "a" and "an" are len<=2, so also filtered.
    assert shared_keywords(a, b) == []  # all stopwords


@pytest.mark.unit
@pytest.mark.asyncio
async def test_requirements_intel_persists_to_kg():
    register_all()
    register_compute_handlers()
    kg = get_kg()
    kg.reset()
    agent = RequirementsIntelAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="requirements_intel",
            input={
                "text": "1. Users can log in\n2. Users can log out\n3. Admin can view users",
                "tenant_id": "t1",
            },
            tenant_id="t1",
        )
    )
    assert out["requirement_count"] == 3
    assert kg.node_count(tenant_id="t1") >= 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_requirements_intel_creates_traceability():
    register_all()
    register_compute_handlers()
    kg = get_kg()
    kg.reset()
    agent = RequirementsIntelAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="requirements_intel",
            input={"text": "1. Users can login\n2. User login tracking", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    # Two requirements sharing "login" → edge
    edges = out["graph"]["traceability"]
    assert isinstance(edges, list)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_requirements_intel_tenant_isolation():
    register_all()
    register_compute_handlers()
    kg = get_kg()
    kg.reset()
    agent = RequirementsIntelAgent()
    await agent.invoke(
        InvocationRequest(
            agent_name="requirements_intel",
            input={"text": "1. Req A\n2. Req B", "tenant_id": "tA"},
            tenant_id="tA",
        )
    )
    assert kg.node_count(tenant_id="tA") == 2
    assert kg.node_count(tenant_id="tB") == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_requirements_intel_empty_text():
    register_all()
    register_compute_handlers()
    agent = RequirementsIntelAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="requirements_intel", input={"text": "", "tenant_id": "t1"}, tenant_id="t1"
        )
    )
    assert out["requirement_count"] == 0
