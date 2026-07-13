"""Tests for  Accessibility Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest

from agents import register_all, register_compute_handlers
from agents.execution.accessibility import AccessibilityAgent

SAMPLE_GOOD = """
<!DOCTYPE html>
<html lang="en">
<body>
  <h1>Welcome</h1>
  <form>
    <label for="u">Username</label>
    <input id="u" name="username" type="text" />
    <button type="submit">Sign in</button>
  </form>
  <img src="/a.png" alt="Logo" />
</body>
</html>
"""


SAMPLE_BAD = """
<!DOCTYPE html>
<html>
<body>
  <form>
    <input type="text" />
    <button></button>
  </form>
  <img src="/a.png" />
</body>
</html>
"""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a11y_passes_clean_html():
    register_all()
    register_compute_handlers()
    agent = AccessibilityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="accessibility",
            input={"dom_html": SAMPLE_GOOD, "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert out["passed"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a11y_detects_missing_alt():
    register_all()
    register_compute_handlers()
    agent = AccessibilityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="accessibility",
            input={"dom_html": SAMPLE_BAD, "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert any(i["rule"] == "image-alt" for i in out["issues"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a11y_detects_missing_label():
    register_all()
    register_compute_handlers()
    agent = AccessibilityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="accessibility",
            input={"dom_html": SAMPLE_BAD, "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert any(i["rule"] == "label" for i in out["issues"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a11y_detects_button_without_name():
    register_all()
    register_compute_handlers()
    agent = AccessibilityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="accessibility",
            input={"dom_html": SAMPLE_BAD, "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert any(i["rule"] == "button-name" for i in out["issues"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a11y_detects_missing_h1():
    register_all()
    register_compute_handlers()
    bad = "<html><body><p>no heading</p></body></html>"
    agent = AccessibilityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="accessibility", input={"dom_html": bad, "tenant_id": "t1"}, tenant_id="t1"
        )
    )
    assert any(i["rule"] == "page-has-h1" for i in out["issues"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a11y_detects_missing_html_lang():
    register_all()
    register_compute_handlers()
    agent = AccessibilityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="accessibility",
            input={"dom_html": SAMPLE_BAD, "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    assert any(i["rule"] == "html-has-lang" for i in out["issues"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a11y_includes_remediation_hint():
    register_all()
    register_compute_handlers()
    agent = AccessibilityAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="accessibility",
            input={"dom_html": SAMPLE_BAD, "tenant_id": "t1"},
            tenant_id="t1",
        )
    )
    for issue in out["issues"]:
        assert issue["remediation"]
