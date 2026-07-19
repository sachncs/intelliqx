"""Smoke tests for the hardened service."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from intelliqx_observability.logging import reset_logging
from intelliqx_service.app import create_app
from intelliqx_service.state import RunStatus


def _token_header() -> dict[str, str]:
    return {"authorization": f"Bearer {os.environ['INTELLIQX_API_TOKEN']}"}


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = tmp_path / "state.db"
    okf = tmp_path / "okf.db"
    monkeypatch.setenv("INTELLIQX_API_TOKEN", "test-token")
    monkeypatch.setenv("INTELLIQX_STATE_DB", str(db))
    monkeypatch.setenv("INTELLIQX_OKF_DB", str(okf))
    monkeypatch.setenv("INTELLIQX_WORKERS", "1")
    reset_logging()
    from intelliqx_compute.runtime import reset_compute_runtime

    reset_compute_runtime()
    app_ = create_app()
    yield app_


@pytest.mark.asyncio
async def test_healthz_is_public(app) -> None:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_runs_endpoint_requires_token(app) -> None:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/runs", json={"agent": "smoke", "tenant_id": "t1", "input": {}}
            )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_full_run_lifecycle(app) -> None:
    """Submit a run, wait for the worker, and assert the structured output."""
    from pydantic import BaseModel
    from pydantic_ai import Agent
    from pydantic_ai.models.test import TestModel

    from agents import AGENT_CATALOG, build_catalog

    class SmokeOut(BaseModel):
        echo: dict

    test_agent = Agent(
        model=TestModel(custom_output_args={"echo": {"k": 1}}),
        output_type=SmokeOut,
        instructions="echo",
    )

    build_catalog()
    for role in AGENT_CATALOG:
        if role.name == "smoke":

            def make_test_agent(*args: Any, **kwargs: Any) -> Any:
                return test_agent

            object.__setattr__(role, "builder", make_test_agent)
            break

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/runs",
                headers=_token_header(),
                json={"agent": "smoke", "tenant_id": "t1", "input": {"k": 1}},
            )
            assert response.status_code == 202
            run_id = response.json()["run_id"]
            for _ in range(50):
                response = await client.get(f"/v1/runs/{run_id}", headers=_token_header())
                if response.json()["status"] in {RunStatus.SUCCEEDED.value, RunStatus.FAILED.value}:
                    break
                await asyncio.sleep(0.05)
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == RunStatus.SUCCEEDED.value
            assert payload["output"] == {"echo": {"k": 1}}
