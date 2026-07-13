"""Execution Agent (Tier 3).

Runs structured test specs against a running environment. The agent
takes a list of :class:`TestSpec` records and executes each one
step-by-step over HTTP. The supported step actions are:

* ``get``              — ``GET <path>``, optionally asserting the
                        response status.
* ``post``             — ``POST <path>`` with a JSON body,
                        optionally asserting the response status.
* ``assert_status``    — ``GET <path>`` and assert the status code.
* ``assert_json``      — ``GET <path>`` and assert that every
                        key/value in ``expected_json`` matches the
                        response body (exact equality).

The agent is the abstraction layer between the Tier 2 "test design"
output and the actual HTTP traffic. In production, the same
:class:`TestSpec` shape can be translated to Playwright / Selenium
calls — the only change is the runner, not the agent.

Test artifacts (per-test result JSON) are uploaded to the object
store at ``{tenant}/runs/{test_name}.json`` for later inspection
by the Reporting agent.
"""

from __future__ import annotations

import time
from typing import Any, ClassVar

import httpx
from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory
from intelliqx_storage.store import get_object_store
from pydantic import BaseModel, ConfigDict, Field


class TestStep(BaseModel):
    # ``pytest`` interprets any class named ``Test*`` as a test class
    # by default. Disable collection so the Pydantic data model is
    # never mistaken for a test case.
    __test__ = False
    model_config = ConfigDict(extra="forbid")

    action: str  # get | post | assert_status | assert_json
    path: str | None = None
    payload: dict[str, Any] | None = None
    expected_status: int | None = None
    expected_json: dict[str, Any] | None = None


class TestSpec(BaseModel):
    # ``pytest`` interprets any class named ``Test*`` as a test class
    # by default. Disable collection so the Pydantic data model is
    # never mistaken for a test case.
    __test__ = False
    model_config = ConfigDict(extra="forbid")

    name: str
    steps: list[TestStep] = Field(default_factory=list)


class ExecutionInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    base_url: str
    tests: list[TestSpec]
    tenant_id: str
    upload_artifacts: bool = True


class StepResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    status: str
    duration_ms: int = 0
    response: dict[str, Any] | None = None
    error: str | None = None


class TestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: str  # passed | failed
    duration_ms: int = 0
    steps: list[StepResult] = Field(default_factory=list)


class ExecutionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[TestResult] = Field(default_factory=list)
    passed: int = 0
    failed: int = 0
    artifact_keys: list[str] = Field(default_factory=list)


class ExecutionAgent(AgentBase):
    META = AgentMeta(
        name="execution",
        category=AgentCategory.EXECUTION,
        version="0.1.0",
        description="Runs structured test specs against an environment.",
    )
    INPUT_MODEL = ExecutionInput
    OUTPUT_MODEL = ExecutionOutput

    # Per-step HTTP timeout. Long enough for slow CI endpoints,
    # short enough to keep CI wall-clock predictable.
    DEFAULT_TIMEOUT_SECONDS: ClassVar[float] = 30.0

    @traced_agent("execution")
    async def run(self, ctx: AgentContext, input: ExecutionInput) -> ExecutionOutput:
        results: list[TestResult] = []
        artifact_keys: list[str] = []
        # Single client across all tests so we reuse the
        # connection pool. Tests that need isolation should run
        # in separate Execution invocations.
        async with httpx.AsyncClient(
            base_url=input.base_url, timeout=self.DEFAULT_TIMEOUT_SECONDS
        ) as client:
            for spec in input.tests:
                tr = await _run_test(client, spec)
                results.append(tr)
        passed = sum(1 for r in results if r.status == "passed")
        failed = sum(1 for r in results if r.status == "failed")
        if input.upload_artifacts:
            store = get_object_store()
            for tr in results:
                key = f"{input.tenant_id}/runs/{tr.name}.json"
                blob = tr.model_dump_json().encode("utf-8")
                await store.put(key, blob, content_type="application/json")
                artifact_keys.append(key)
        return ExecutionOutput(
            results=results, passed=passed, failed=failed, artifact_keys=artifact_keys
        )


async def _run_test(client: httpx.AsyncClient, spec: TestSpec) -> TestResult:
    """Run a single test spec.

    A test is ``"passed"`` iff every step's status is ``"passed"``;
    otherwise the test is ``"failed"``. Step failures do not abort
    the spec — we keep going so a single broken step doesn't hide
    later ones.
    """
    start = time.monotonic()
    step_results: list[StepResult] = []
    failed = False
    for step in spec.steps:
        s_start = time.monotonic()
        try:
            if step.action == "get":
                r = await client.get(step.path or "/")
                if step.expected_status is not None and r.status_code != step.expected_status:
                    failed = True
                    step_results.append(
                        StepResult(
                            action=step.action,
                            status="failed",
                            duration_ms=int((time.monotonic() - s_start) * 1000),
                            error=f"expected {step.expected_status}, got {r.status_code}",
                        )
                    )
                else:
                    step_results.append(
                        StepResult(
                            action=step.action,
                            status="passed",
                            duration_ms=int((time.monotonic() - s_start) * 1000),
                            response={"status_code": r.status_code, "body": _safe_json(r)},
                        )
                    )
            elif step.action == "post":
                r = await client.post(step.path or "/", json=step.payload or {})
                if step.expected_status is not None and r.status_code != step.expected_status:
                    failed = True
                    step_results.append(
                        StepResult(
                            action=step.action,
                            status="failed",
                            duration_ms=int((time.monotonic() - s_start) * 1000),
                            error=f"expected {step.expected_status}, got {r.status_code}",
                        )
                    )
                else:
                    step_results.append(
                        StepResult(
                            action=step.action,
                            status="passed",
                            duration_ms=int((time.monotonic() - s_start) * 1000),
                            response={"status_code": r.status_code, "body": _safe_json(r)},
                        )
                    )
            elif step.action == "assert_status":
                r = await client.get(step.path or "/")
                ok = r.status_code == (step.expected_status or 200)
                if not ok:
                    failed = True
                step_results.append(
                    StepResult(
                        action=step.action,
                        status="passed" if ok else "failed",
                        duration_ms=int((time.monotonic() - s_start) * 1000),
                        error=None if ok else f"got {r.status_code}",
                    )
                )
            elif step.action == "assert_json":
                r = await client.get(step.path or "/")
                body = _safe_json(r) or {}
                ok = all(body.get(k) == v for k, v in (step.expected_json or {}).items())
                if not ok:
                    failed = True
                step_results.append(
                    StepResult(
                        action=step.action,
                        status="passed" if ok else "failed",
                        duration_ms=int((time.monotonic() - s_start) * 1000),
                        response=body if ok else None,
                        error=None if ok else "json assertion failed",
                    )
                )
            else:
                failed = True
                step_results.append(
                    StepResult(
                        action=step.action,
                        status="failed",
                        duration_ms=int((time.monotonic() - s_start) * 1000),
                        error=f"unknown action: {step.action}",
                    )
                )
        except Exception as e:
            failed = True
            step_results.append(
                StepResult(
                    action=step.action,
                    status="error",
                    duration_ms=int((time.monotonic() - s_start) * 1000),
                    error=f"{type(e).__name__}: {e}",
                )
            )
    duration_ms = int((time.monotonic() - start) * 1000)
    return TestResult(
        name=spec.name,
        status="failed" if failed else "passed",
        duration_ms=duration_ms,
        steps=step_results,
    )


def _safe_json(r: httpx.Response) -> dict[str, Any] | None:
    """Parse a response as JSON, returning ``None`` on failure."""
    try:
        return r.json()
    except Exception:
        return None
