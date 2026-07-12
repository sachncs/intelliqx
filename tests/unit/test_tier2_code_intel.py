"""Tests for Tier 2 Code Intelligence Agent."""

import pytest
from aqip_compute.runtime import InvocationRequest
from aqip_kg.graph import get_kg

from agents import register_all, register_compute_handlers
from agents.tier2.code_intel import CodeIntelAgent, _extract_imports


@pytest.mark.unit
def test_extract_imports_basic():
    src = """
import os
from typing import Any
from agents.tier1.planner import PlannerAgent
"""
    deps = _extract_imports(src)
    assert "os" in deps
    assert "typing" in deps
    assert "agents.tier1.planner" in deps


@pytest.mark.unit
def test_extract_imports_empty():
    assert _extract_imports("") == set()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_code_intel_indexes_files():
    register_all()
    register_compute_handlers()
    kg = get_kg()
    kg.reset()
    agent = CodeIntelAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="code_intel",
            input={
                "files": [
                    {"path": "src/a.py", "content": "import os\n"},
                    {"path": "src/b.py", "content": "from a import hello\n"},
                ],
                "tenant_id": "t1",
                "changed_paths": [],
            },
            tenant_id="t1",
        )
    )
    assert out["files_indexed"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_code_intel_finds_dependencies():
    register_all()
    register_compute_handlers()
    agent = CodeIntelAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="code_intel",
            input={
                "files": [
                    {"path": "src/a.py", "content": ""},
                    {"path": "src/b.py", "content": "from a import x\n"},
                ],
                "tenant_id": "t1",
                "changed_paths": [],
            },
            tenant_id="t1",
        )
    )
    assert len(out["graph"]["dependencies"]) >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_code_intel_impact_when_no_changes():
    register_all()
    register_compute_handlers()
    agent = CodeIntelAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="code_intel",
            input={
                "files": [
                    {"path": "src/a.py", "content": ""},
                    {"path": "src/b.py", "content": ""},
                ],
                "tenant_id": "t1",
                "changed_paths": [],
            },
            tenant_id="t1",
        )
    )
    # No changes → all files considered affected
    assert set(out["graph"]["affected_files"]) == {"src/a.py", "src/b.py"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_code_intel_impact_with_changes():
    register_all()
    register_compute_handlers()
    kg = get_kg()
    kg.reset()
    agent = CodeIntelAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="code_intel",
            input={
                "files": [
                    {"path": "src/a.py", "content": ""},
                    {"path": "src/b.py", "content": "from a import x\n"},
                ],
                "tenant_id": "t1",
                "changed_paths": ["src/a.py"],
            },
            tenant_id="t1",
        )
    )
    affected = set(out["graph"]["affected_files"])
    assert "src/a.py" in affected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_code_intel_persists_to_kg():
    register_all()
    register_compute_handlers()
    kg = get_kg()
    kg.reset()
    agent = CodeIntelAgent()
    await agent.invoke(
        InvocationRequest(
            agent_name="code_intel",
            input={
                "files": [
                    {"path": "src/a.py", "content": "import os"},
                    {"path": "src/b.py", "content": ""},
                ],
                "tenant_id": "t1",
                "changed_paths": [],
            },
            tenant_id="t1",
        )
    )
    assert kg.node_count(tenant_id="t1") >= 2