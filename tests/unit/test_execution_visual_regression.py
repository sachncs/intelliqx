"""Tests for Tier 3 Visual Regression Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest
from intelliqx_storage.store import InMemoryObjectStore

from agents import register_all, register_compute_handlers
from agents.execution.visual_regression import VisualRegressionAgent, _pixel_diff_pct


@pytest.mark.unit
def test_pixel_diff_pct_zero_for_identical():
    assert _pixel_diff_pct(b"hello", b"hello") == 0.0


@pytest.mark.unit
def test_pixel_diff_pct_nonzero_for_different():
    assert _pixel_diff_pct(b"hello", b"world") > 0.0


@pytest.mark.unit
def test_pixel_diff_pct_caps_at_one():
    assert _pixel_diff_pct(b"a", b"b" * 100) <= 1.0


@pytest.mark.unit
def test_pixel_diff_pct_empty():
    assert _pixel_diff_pct(b"", b"abc") == 1.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_visual_regression_stores_baseline_on_first_run():
    from intelliqx_storage.store import reset_object_store, set_object_store

    register_all()
    register_compute_handlers()
    # Install a fresh in-memory store for this test so we can
    # inspect what the agent wrote.
    reset_object_store()
    storage = InMemoryObjectStore()
    set_object_store(storage)
    agent = VisualRegressionAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="visual_regression",
            input={
                "tenant_id": "t1",
                "image_bytes": b"baseline-image-data",
                "baseline_key": "t1/visual/baseline.png",
                "name": "home",
            },
            tenant_id="t1",
        )
    )
    assert not out["is_regression"]
    assert out["baseline_hash"] == ""
    assert out["current_hash"] != ""
    stored = await storage.get("t1/visual/baseline.png")
    assert stored == b"baseline-image-data"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_visual_regression_detects_regression():
    register_all()
    register_compute_handlers()
    agent = VisualRegressionAgent()
    # First run sets baseline
    await agent.invoke(
        InvocationRequest(
            agent_name="visual_regression",
            input={
                "tenant_id": "t1",
                "image_bytes": b"original",
                "baseline_key": "t1/visual/b.png",
            },
            tenant_id="t1",
        )
    )
    # Second run with different bytes → regression
    out = await agent.invoke(
        InvocationRequest(
            agent_name="visual_regression",
            input={"tenant_id": "t1", "image_bytes": b"x" * 100, "baseline_key": "t1/visual/b.png"},
            tenant_id="t1",
        )
    )
    assert out["is_regression"]
    assert out["diff_pct"] > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_visual_regression_identical_pass():
    register_all()
    register_compute_handlers()
    agent = VisualRegressionAgent()
    await agent.invoke(
        InvocationRequest(
            agent_name="visual_regression",
            input={"tenant_id": "t1", "image_bytes": b"same", "baseline_key": "t1/visual/s.png"},
            tenant_id="t1",
        )
    )
    out = await agent.invoke(
        InvocationRequest(
            agent_name="visual_regression",
            input={"tenant_id": "t1", "image_bytes": b"same", "baseline_key": "t1/visual/s.png"},
            tenant_id="t1",
        )
    )
    assert not out["is_regression"]
    assert out["diff_pct"] == 0.0
