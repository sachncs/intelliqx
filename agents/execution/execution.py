"""Execution Agent (Execution).

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

The agent is the abstraction layer between the Intelligence "test design"
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
    """A named test comprising an ordered list of :class:`TestStep`.

    Attributes:
        name: Human-readable test name. Used as the artifact
            filename in the object store.
        steps: Ordered list of steps to execute. Step failures do
            not abort the spec — every step is attempted so a single
            broken step doesn't hide later ones.
    """

    # ``pytest`` interprets any class named ``Test*`` as a test class
    # by default. Disable collection so the Pydantic data model is
    # never mistaken for a test case.
    __test__ = False
    model_config = ConfigDict(extra="forbid")

    name: str
    steps: list[TestStep] = Field(default_factory=list)


class ExecutionInput(BaseModel):
    """Input payload for the Execution agent.

    Attributes:
        base_url: Root URL of the system under test (e.g.
            ``"http://localhost:8000"``).
        tests: Specs to execute. The agent reuses one ``httpx``
            client across all tests in the list for connection-
            pool efficiency.
        tenant_id: Owning tenant; used as the artifact prefix in
            the object store.
        upload_artifacts: When ``True`` (default), per-test result
            JSON is uploaded to the object store at
            ``{tenant}/runs/{test_name}.json``.
    """

    model_config = ConfigDict(extra="ignore")

    base_url: str
    tests: list[TestSpec]
    tenant_id: str
    upload_artifacts: bool = True


class StepResult(BaseModel):
    """Result of a single :class:`TestStep` execution.

    Attributes:
        action: Echo of the step's action.
        status: ``"passed"``, ``"failed"``, or ``"error"``.
            ``"error"`` is reserved for exceptions raised by the
            HTTP client; ``"failed"`` is for assertion mismatches.
        duration_ms: Wall-clock duration of the step.
        response: Captured ``{"status_code": int, "body": Any}`` on
            success; ``None`` on failure.
        error: Error message on failure; ``None`` on success.
    """

    model_config = ConfigDict(extra="forbid")

    action: str
    status: str
    duration_ms: int = 0
    response: dict[str, Any] | None = None
    error: str | None = None


class TestResult(BaseModel):
    """Result of a single :class:`TestSpec` execution.

    Attributes:
        name: Echo of the spec name.
        status: ``"passed"`` iff every step passed; ``"failed"``
            otherwise.
        duration_ms: Wall-clock duration of the entire spec.
        steps: Per-step results, in execution order.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    status: str  # passed | failed
    duration_ms: int = 0
    steps: list[StepResult] = Field(default_factory=list)


class ExecutionOutput(BaseModel):
    """Output payload for the Execution agent.

    Attributes:
        results: Per-test results in execution order.
        passed: Count of tests with status ``"passed"``.
        failed: Count of tests with status ``"failed"``.
        artifact_keys: Object-store keys for every per-test
            artifact uploaded.
    """

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
                tr = await run_test(client, spec)
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


async def run_test(client: httpx.AsyncClient, spec: TestSpec) -> TestResult:
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
                            response={"status_code": r.status_code, "body": safe_json(r)},
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
                            response={"status_code": r.status_code, "body": safe_json(r)},
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
                body = safe_json(r) or {}
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


def safe_json(r: httpx.Response) -> dict[str, Any] | None:
    """Parse an ``httpx.Response`` body as JSON.

    Args:
        r: The response to parse.

    Returns:
        The parsed JSON document, or ``None`` if the body is empty
        or not valid JSON. Used so non-JSON responses don't abort
        the whole spec — they just record a non-JSON body.
    """
    try:
        return r.json()
    except Exception:
        return None
