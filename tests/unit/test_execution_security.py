"""Tests for  Security Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest

from agents import register_all, register_compute_handlers
from agents.execution.security import SecurityAgent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_security_finds_akia_access_key():
    register_all()
    register_compute_handlers()
    agent = SecurityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="security",
            input={
                "tenant_id": "t1",
                "source_files": {"config.py": "ACCESS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n"},
            },
            tenant_id="t1",
        )
    )
    assert any(f["type"] == "secret" and "Access Key" in f["message"] for f in out["findings"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_security_finds_eval():
    register_all()
    register_compute_handlers()
    agent = SecurityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="security",
            input={"tenant_id": "t1", "source_files": {"app.py": "x = eval(input())\n"}},
            tenant_id="t1",
        )
    )
    assert any(f["type"] == "sast" for f in out["findings"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_security_finds_pickle():
    register_all()
    register_compute_handlers()
    agent = SecurityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="security",
            input={"tenant_id": "t1", "source_files": {"app.py": "data = pickle.loads(blob)\n"}},
            tenant_id="t1",
        )
    )
    # Both eval/exec and pickle patterns match
    assert any(f["severity"] == "critical" for f in out["findings"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_security_finds_outdated_django():
    register_all()
    register_compute_handlers()
    agent = SecurityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="security",
            input={"tenant_id": "t1", "source_files": {"requirements.txt": "django==1.11.0\n"}},
            tenant_id="t1",
        )
    )
    assert any(f["type"] == "dependency" for f in out["findings"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_security_clean_code_no_findings():
    register_all()
    register_compute_handlers()
    agent = SecurityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="security",
            input={
                "tenant_id": "t1",
                "source_files": {"safe.py": "def add(a, b):\n    return a + b\n"},
            },
            tenant_id="t1",
        )
    )
    assert out["findings"] == []
    assert out["critical"] == 0
    assert out["high"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_security_dast_checks_headers():
    register_all()
    register_compute_handlers()
    agent = SecurityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="security",
            input={
                "tenant_id": "t1",
                "source_files": {},
                "target_url": "http://127.0.0.1:1",  # intentionally unreachable
            },
            tenant_id="t1",
        )
    )
    # Should still produce a DAST finding (probe failure)
    dast = [f for f in out["findings"] if f["type"] == "dast"]
    assert dast


@pytest.mark.unit
@pytest.mark.asyncio
async def test_security_counts_critical_and_high():
    register_all()
    register_compute_handlers()
    agent = SecurityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="security",
            input={
                "tenant_id": "t1",
                "source_files": {
                    "app.py": (
                        "ACCESS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n"
                        "x = eval(input())\n"
                        "data = pickle.loads(blob)\n"
                    )
                },
            },
            tenant_id="t1",
        )
    )
    assert out["critical"] >= 2  # access key + pickle
    assert out["high"] >= 1  # eval
