"""Tests for Tier 3 Design Intelligence Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest
from intelliqx_kg.graph import get_kg

from agents import register_all, register_compute_handlers
from agents.tier3.design_intel import DesignIntelAgent, UIElement, _infer_workflow, _parse_dom

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<body>
  <header>
    <h1 id="title">IntelliqX</h1>
    <nav><a href="/login" id="nav-login">Login</a></nav>
  </header>
  <main>
    <form id="login-form" action="/login" method="post">
      <label for="username">Username</label>
      <input id="username" name="username" type="text" />
      <button type="submit" id="submit-btn">Sign in</button>
    </form>
  </main>
</body>
</html>
"""


@pytest.mark.unit
def test_parse_dom_extracts_elements():
    elements = _parse_dom(SAMPLE_HTML)
    ids = {e.id for e in elements}
    assert "title" in ids
    assert "username" in ids
    assert "submit-btn" in ids


@pytest.mark.unit
def test_parse_dom_selector_format():
    elements = _parse_dom(SAMPLE_HTML)
    title = next((e for e in elements if e.id == "title"), None)
    assert title is not None
    assert title.selector == "#title"
    assert title.tag == "h1"


@pytest.mark.unit
def test_infer_workflow_with_form_and_button():
    elements = _parse_dom(SAMPLE_HTML)
    steps = _infer_workflow(elements)
    assert "Fill form fields" in steps
    assert "Click submit button" in steps


@pytest.mark.unit
def test_infer_workflow_with_links_only():
    elements = [UIElement(tag="a", selector="#x")]
    steps = _infer_workflow(elements)
    assert "Navigate via links" in steps


@pytest.mark.unit
@pytest.mark.asyncio
async def test_design_intel_persists_to_kg():
    register_all()
    register_compute_handlers()
    kg = get_kg()
    kg.reset()
    agent = DesignIntelAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="design_intel",
            input={"dom_html": SAMPLE_HTML, "base_url": "http://x", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert len(out["elements"]) >= 3
    assert kg.node_count(tenant_id="t1") >= 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_design_intel_returns_workflow_steps():
    register_all()
    register_compute_handlers()
    agent = DesignIntelAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="design_intel",
            input={"dom_html": SAMPLE_HTML, "base_url": "http://x", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert len(out["workflow_steps"]) >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_design_intel_handles_empty_html():
    register_all()
    register_compute_handlers()
    agent = DesignIntelAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="design_intel",
            input={"dom_html": "", "base_url": "http://x", "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert out["elements"] == []