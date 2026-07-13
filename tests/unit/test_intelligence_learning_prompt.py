"""Tests for  Learning and Prompt Management agents."""

import pytest
from intelliqx_compute.runtime import InvocationRequest
from intelliqx_state.store import get_state_store

from agents import register_all, register_compute_handlers
from agents.intelligence.learning import LearningAgent
from agents.intelligence.prompt_management import PromptManagementAgent

# --- Learning ----------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_learning_persists_feedback():
    register_all()
    register_compute_handlers()
    agent = LearningAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="learning",
            input={
                "tenant_id": "t1",
                "run_id": "r1",
                "feedback": {"prompt_id": "p1", "outcome": "passed"},
            },
            tenant_id="t1",
        )
    )
    assert out["recommendations"] == []
    state = get_state_store()
    blob = await state.get("learning:t1:r1")
    assert blob is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_learning_deprecates_low_passing_prompt():
    import json

    register_all()
    register_compute_handlers()
    state = get_state_store()
    # Seed history: 4 failed, 1 passed for prompt p1
    for i in range(5):
        await state.set(
            f"learning:t1:run-seed-{i}",
            json.dumps({"prompt_id": "p1", "outcome": "passed" if i == 0 else "failed"}).encode(),
            ttl_seconds=3600,
        )
    agent = LearningAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="learning",
            input={
                "tenant_id": "t1",
                "run_id": "r-new",
                "feedback": {"prompt_id": "p1", "outcome": "passed"},
            },
            tenant_id="t1",
        )
    )
    actions = [r["action"] for r in out["recommendations"]]
    assert "deprecate" in actions


@pytest.mark.unit
@pytest.mark.asyncio
async def test_learning_promotes_high_passing_prompt():
    import json

    register_all()
    register_compute_handlers()
    state = get_state_store()
    for i in range(20):
        await state.set(
            f"learning:t1:run-{i}",
            json.dumps({"prompt_id": "p_good", "outcome": "passed"}).encode(),
            ttl_seconds=3600,
        )
    agent = LearningAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="learning",
            input={"tenant_id": "t1", "run_id": "r-x", "feedback": {}},
            tenant_id="t1",
        )
    )
    actions = [r["action"] for r in out["recommendations"]]
    assert "promote_as_default" in actions


# --- Prompt Management -------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prompt_register_and_list():
    register_all()
    register_compute_handlers()
    agent = PromptManagementAgent()
    await agent.invoke(
        InvocationRequest(
            agent_name="prompt_management",
            input={
                "action": "register",
                "tenant_id": "t1",
                "prompt_id": "p1",
                "version": "v1",
                "text": "You are a QA agent.",
            },
            tenant_id="t1",
        )
    )
    out = await agent.invoke(
        InvocationRequest(
            agent_name="prompt_management",
            input={"action": "list", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert any(p["prompt_id"] == "p1" and p["version"] == "v1" for p in out["prompts"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prompt_register_multiple_versions():
    register_all()
    register_compute_handlers()
    agent = PromptManagementAgent()
    for v in ("v1", "v2", "v3"):
        await agent.invoke(
            InvocationRequest(
                agent_name="prompt_management",
                input={
                    "action": "register",
                    "tenant_id": "t1",
                    "prompt_id": "p1",
                    "version": v,
                    "text": f"prompt {v}",
                },
                tenant_id="t1",
            )
        )
    out = await agent.invoke(
        InvocationRequest(
            agent_name="prompt_management",
            input={"action": "list", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    versions = sorted(p["version"] for p in out["prompts"] if p["prompt_id"] == "p1")
    assert versions == ["v1", "v2", "v3"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prompt_ab_record():
    register_all()
    register_compute_handlers()
    agent = PromptManagementAgent()
    await agent.invoke(
        InvocationRequest(
            agent_name="prompt_management",
            input={
                "action": "register",
                "tenant_id": "t1",
                "prompt_id": "p1",
                "version": "v1",
                "text": "x",
            },
            tenant_id="t1",
        )
    )
    for _ in range(5):
        await agent.invoke(
            InvocationRequest(
                agent_name="prompt_management",
                input={
                    "action": "ab_record",
                    "tenant_id": "t1",
                    "prompt_id": "p1",
                    "version": "v1",
                    "outcome": "passed",
                },
                tenant_id="t1",
            )
        )
    state = get_state_store()
    n = int((await state.get("ab:t1:p1:v1")).decode())
    p = int((await state.get("ab_pass:t1:p1:v1")).decode())
    assert n == 5
    assert p == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prompt_bandit_select_returns_version():
    register_all()
    register_compute_handlers()
    agent = PromptManagementAgent()
    for v, n_pass, n_total in (("v1", 5, 5), ("v2", 4, 10)):
        await agent.invoke(
            InvocationRequest(
                agent_name="prompt_management",
                input={
                    "action": "register",
                    "tenant_id": "t1",
                    "prompt_id": "p1",
                    "version": v,
                    "text": v,
                },
                tenant_id="t1",
            )
        )
        for _ in range(n_total):
            await agent.invoke(
                InvocationRequest(
                    agent_name="prompt_management",
                    input={
                        "action": "ab_record",
                        "tenant_id": "t1",
                        "prompt_id": "p1",
                        "version": v,
                        "outcome": "passed",
                    },
                    tenant_id="t1",
                )
            )
            if n_pass > 0:
                n_pass -= 1
    sel = await agent.invoke(
        InvocationRequest(
            agent_name="prompt_management",
            input={"action": "select", "tenant_id": "t1", "prompt_id": "p1"},
            tenant_id="t1",
        )
    )
    assert sel["selected"] is not None
    assert sel["selected"]["prompt_id"] == "p1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prompt_select_unknown_returns_none():
    register_all()
    register_compute_handlers()
    agent = PromptManagementAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="prompt_management",
            input={"action": "select", "tenant_id": "t1", "prompt_id": "missing"},
            tenant_id="t1",
        )
    )
    assert out["selected"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prompt_unknown_action():
    register_all()
    register_compute_handlers()
    agent = PromptManagementAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="prompt_management",
            input={"action": "wat", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert out["prompts"] == []
    assert out["selected"] is None
