"""Tests for Tier 3 Self-Healing Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest

from agents import register_all, register_compute_handlers
from agents.execution.self_healing import SelfHealingAgent, _generate_candidates

SAMPLE_HTML = """
<form id="login-form">
  <input id="username" name="username" />
  <input id="password" name="password" type="password" />
  <button id="submit-btn" type="submit">Sign in</button>
</form>
<a id="nav-forgot" data-testid="forgot-pw-link" aria-label="Forgot password">Forgot?</a>
"""


@pytest.mark.unit
def test_candidates_include_id():
    cands = _generate_candidates("#old-id", SAMPLE_HTML)
    selectors = [c.selector for c in cands]
    assert "#username" in selectors
    assert "#submit-btn" in selectors


@pytest.mark.unit
def test_candidates_include_data_testid():
    cands = _generate_candidates("#x", SAMPLE_HTML)
    selectors = [c.selector for c in cands]
    assert '[data-testid="forgot-pw-link"]' in selectors


@pytest.mark.unit
def test_candidates_include_name_attr():
    cands = _generate_candidates("#x", SAMPLE_HTML)
    selectors = [c.selector for c in cands]
    assert '[name="username"]' in selectors


@pytest.mark.unit
def test_candidates_include_aria_label():
    cands = _generate_candidates("#x", SAMPLE_HTML)
    selectors = [c.selector for c in cands]
    assert '[aria-label="Forgot password"]' in selectors


@pytest.mark.unit
def test_candidates_dedupe():
    cands = _generate_candidates("#x", SAMPLE_HTML)
    selectors = [c.selector for c in cands]
    assert len(selectors) == len(set(selectors))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_self_healing_heals_below_threshold():
    register_all()
    register_compute_handlers()
    agent = SelfHealingAgent()
    # Default min_confidence=0.5; first candidate should be id-based with 0.8
    out = await agent.invoke(
        InvocationRequest(
            agent_name="self_healing",
            input={"failed_selector": "#old-id", "dom_html": SAMPLE_HTML},
            tenant_id="t1",
        )
    )
    assert out["healed"]
    assert out["applied_selector"] is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_self_healing_no_heal_above_threshold():
    register_all()
    register_compute_handlers()
    agent = SelfHealingAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="self_healing",
            input={"failed_selector": "#x", "dom_html": SAMPLE_HTML, "min_confidence": 0.99},
            tenant_id="t1",
        )
    )
    assert not out["healed"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_self_healing_returns_candidates():
    register_all()
    register_compute_handlers()
    agent = SelfHealingAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="self_healing",
            input={"failed_selector": "#x", "dom_html": SAMPLE_HTML, "min_confidence": 0.99},
            tenant_id="t1",
        )
    )
    assert len(out["candidates"]) >= 1
    # Sorted by confidence desc
    confs = [c["confidence"] for c in out["candidates"]]
    assert confs == sorted(confs, reverse=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_self_healing_empty_dom():
    register_all()
    register_compute_handlers()
    agent = SelfHealingAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="self_healing",
            input={"failed_selector": "#x", "dom_html": ""},
            tenant_id="t1",
        )
    )
    assert out["candidates"] == []
    assert not out["healed"]
