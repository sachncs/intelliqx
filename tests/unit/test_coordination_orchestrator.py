"""Orchestrator validation, scheduling, and lifecycle tests."""

import asyncio
import json
import time
from typing import Any

import pytest
from intelliqx_compute.runtime import (
    ComputeRuntime,
    InvocationRequest,
    InvocationResponse,
    get_compute_runtime,
    set_compute_runtime,
)
from intelliqx_core.models import RunStatus
from intelliqx_events.bus import get_event_bus
from intelliqx_state.store import InMemoryStateStore, get_state_store
from pydantic import ValidationError

from agents import register_all, register_compute_handlers
from agents.coordination.orchestrator import OrchestratorAgent


def ensure_registered() -> None:
    register_all()
    register_compute_handlers()


def node(
    node_id: str,
    agent: str = "smoke",
    *,
    depends_on: list[str] | None = None,
    inputs: dict[str, Any] | None = None,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "agent": agent,
        "inputs": inputs or {},
        "depends_on": depends_on or [],
        "timeout_seconds": timeout_seconds,
    }


def request(
    nodes: list[dict[str, Any]],
    *,
    run_id: str = "r1",
    input_tenant: str = "t1",
    request_tenant: str = "t1",
    max_parallel: int = 4,
    max_retries: int = 2,
) -> InvocationRequest:
    return InvocationRequest(
        agent_name="orchestrator",
        input={
            "plan_id": "p1",
            "goal_id": "g1",
            "tenant_id": input_tenant,
            "run_id": run_id,
            "max_parallel": max_parallel,
            "max_retries": max_retries,
            "nodes": nodes,
        },
        tenant_id=request_tenant,
    )


def collect_events() -> list[Any]:
    events: list[Any] = []
    bus = get_event_bus()
    for topic in ("run.started", "plan.node.started", "plan.node.completed", "run.completed"):
        bus.subscribe(topic, events.append)
    return events


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("nodes", "max_parallel", "max_retries"),
    [
        ([], 4, 2),
        ([node("n1")], 0, 2),
        ([node("n1")], 65, 2),
        ([node("n1")], 4, -1),
        ([node("n1")], 4, 6),
        ([node("n1", timeout_seconds=0)], 4, 2),
        ([node("n1", timeout_seconds=3601)], 4, 2),
    ],
)
async def test_orchestrator_rejects_invalid_bounds_before_side_effects(
    nodes: list[dict[str, Any]], max_parallel: int, max_retries: int
) -> None:
    events = collect_events()
    with pytest.raises(ValidationError):
        await OrchestratorAgent().invoke(
            request(nodes, max_parallel=max_parallel, max_retries=max_retries)
        )
    assert events == []
    assert await get_state_store().hgetall("run:r1") == {}


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "nodes",
    [
        [node("n1"), node("n1")],
        [node("n1", depends_on=["missing"])],
        [node("n1", depends_on=["n1"])],
        [node("n1", depends_on=["n2"]), node("n2", depends_on=["n1"])],
    ],
)
async def test_orchestrator_rejects_invalid_dags_before_side_effects(
    nodes: list[dict[str, Any]],
) -> None:
    events = collect_events()
    with pytest.raises(ValidationError):
        await OrchestratorAgent().invoke(request(nodes))
    assert events == []
    assert await get_state_store().hgetall("run:r1") == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_rejects_tenant_mismatch_before_side_effects() -> None:
    events = collect_events()
    with pytest.raises(ValueError, match="tenant_id"):
        await OrchestratorAgent().invoke(
            request([node("n1")], input_tenant="t2", request_tenant="t1")
        )
    assert events == []
    assert await get_state_store().hgetall("run:r1") == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_uses_fresh_correlated_metadata_for_every_event() -> None:
    ensure_registered()
    events = collect_events()
    output = await OrchestratorAgent().invoke(request([node("n1")]))
    assert output["status"] == RunStatus.SUCCEEDED.value
    assert len(events) == 4
    assert len({event.metadata.event_id for event in events}) == 4
    assert len({event.metadata.emitted_at for event in events}) == 4
    assert {event.metadata.correlation_id for event in events} == {"r1"}


class RecordingStateStore(InMemoryStateStore):
    def __init__(self) -> None:
        super().__init__()
        self.statuses: list[str] = []

    async def hset(self, key: str, field: str, value: str) -> None:
        if field == "status":
            self.statuses.append(value)
        await super().hset(key, field, value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_persists_running_and_terminal_hash_with_ttl(monkeypatch) -> None:
    import agents.coordination.orchestrator as orchestrator_module

    ensure_registered()
    state = RecordingStateStore()
    monkeypatch.setattr(orchestrator_module, "get_state_store", lambda: state)
    await OrchestratorAgent().invoke(request([node("n1")], run_id="r-state"))
    values = await state.hgetall("run:r-state")
    assert state.statuses == [RunStatus.RUNNING.value, RunStatus.SUCCEEDED.value]
    assert values["status"] == RunStatus.SUCCEEDED.value
    assert values["plan_id"] == "p1"
    assert values["goal_id"] == "g1"
    assert values["started_at"]
    assert values["completed_at"]
    assert json.loads(values["summary"]) == {"blocked": 0, "failed": 0, "passed": 1, "total": 1}
    assert await state.get("run:r-state") is None
    assert state.expiry["run:r-state"] > time.time()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_retries_only_transport_errors_with_one_event_pair() -> None:
    ensure_registered()
    runtime = get_compute_runtime()
    calls = 0

    async def flaky(_request: InvocationRequest) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient")
        return {"value": calls}

    runtime.register("flaky", flaky)
    events = collect_events()
    output = await OrchestratorAgent().invoke(
        request([node("n1", "flaky")], run_id="r-retry", max_retries=2)
    )
    result = output["node_results"][0]
    assert calls == 2
    assert result["attempts"] == 2
    assert result["status"] == "ok"
    assert result["outcome"] == "passed"
    assert [event.detail_type for event in events].count("PlanNodeStarted") == 1
    completed = [event for event in events if event.detail_type == "PlanNodeCompleted"]
    assert len(completed) == 1
    assert completed[0].attempts == 2
    assert completed[0].outcome == "passed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_does_not_retry_not_found() -> None:
    output = await OrchestratorAgent().invoke(request([node("n1", "missing")], max_retries=5))
    result = output["node_results"][0]
    assert output["status"] == RunStatus.FAILED.value
    assert result["status"] == "not_found"
    assert result["outcome"] == "failed"
    assert result["attempts"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_does_not_retry_domain_failure() -> None:
    runtime = get_compute_runtime()
    calls = 0

    async def domain_failure(_request: InvocationRequest) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"outcome": "failed"}

    runtime.register("domain_failure", domain_failure)
    output = await OrchestratorAgent().invoke(
        request([node("n1", "domain_failure")], max_retries=5)
    )
    result = output["node_results"][0]
    assert calls == 1
    assert output["status"] == RunStatus.FAILED.value
    assert result["status"] == "ok"
    assert result["outcome"] == "failed"
    assert result["attempts"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_blocks_failed_dependency_chain() -> None:
    runtime = get_compute_runtime()
    calls: list[str] = []

    async def fail(_request: InvocationRequest) -> dict[str, Any]:
        calls.append("n1")
        return {"outcome": "failed"}

    async def should_not_run(invocation: InvocationRequest) -> dict[str, Any]:
        calls.append(invocation.agent_name)
        return {}

    runtime.register("fail", fail)
    runtime.register("n2_agent", should_not_run)
    runtime.register("n3_agent", should_not_run)
    events = collect_events()
    output = await OrchestratorAgent().invoke(
        request(
            [
                node("n1", "fail"),
                node("n2", "n2_agent", depends_on=["n1"]),
                node("n3", "n3_agent", depends_on=["n2"]),
            ]
        )
    )
    assert calls == ["n1"]
    assert [result["node_id"] for result in output["node_results"]] == ["n1", "n2", "n3"]
    assert [result["outcome"] for result in output["node_results"]] == [
        "failed",
        "blocked",
        "blocked",
    ]
    assert [result["attempts"] for result in output["node_results"]] == [1, 0, 0]
    started = [event.node_id for event in events if event.detail_type == "PlanNodeStarted"]
    completed = [event for event in events if event.detail_type == "PlanNodeCompleted"]
    assert started == ["n1"]
    assert [event.node_id for event in completed] == ["n1", "n2", "n3"]
    assert [event.outcome for event in completed] == ["failed", "blocked", "blocked"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_returns_parallel_results_in_plan_order() -> None:
    runtime = get_compute_runtime()

    async def delayed(invocation: InvocationRequest) -> dict[str, Any]:
        await asyncio.sleep(invocation.input["delay"])
        return {"value": invocation.input["value"]}

    runtime.register("delayed", delayed)
    output = await OrchestratorAgent().invoke(
        request(
            [
                node("slow", "delayed", inputs={"delay": 0.03, "value": 1}),
                node("fast", "delayed", inputs={"delay": 0.001, "value": 2}),
                node("middle", "delayed", inputs={"delay": 0.01, "value": 3}),
            ],
            max_parallel=3,
        )
    )
    assert [result["node_id"] for result in output["node_results"]] == ["slow", "fast", "middle"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_fails_release_no_go() -> None:
    ensure_registered()
    output = await OrchestratorAgent().invoke(
        request(
            [
                node(
                    "release",
                    "release_readiness",
                    inputs={
                        "tenant_id": "t1",
                        "risk_score": 0.2,
                        "coverage_pct": 85,
                        "security_findings_critical": 5,
                    },
                )
            ]
        )
    )
    result = output["node_results"][0]
    assert output["status"] == RunStatus.FAILED.value
    assert result["status"] == "ok"
    assert result["outcome"] == "failed"
    assert result["output"]["recommendation"] == "no_go"


class TimeoutThenOkRuntime(ComputeRuntime):
    def __init__(self) -> None:
        self.calls = 0

    async def invoke(self, request: InvocationRequest) -> InvocationResponse:
        self.calls += 1
        if self.calls == 1:
            return InvocationResponse(
                agent_name=request.agent_name,
                output={},
                duration_ms=1,
                status="timeout",
                error="Invocation timed out",
            )
        return InvocationResponse(
            agent_name=request.agent_name, output={}, duration_ms=1, status="ok"
        )

    def register(self, agent_name: str, handler) -> None:
        pass


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_retries_transport_timeout() -> None:
    runtime = TimeoutThenOkRuntime()
    set_compute_runtime(runtime)
    output = await OrchestratorAgent().invoke(request([node("n1", "slow")], max_retries=1))
    assert runtime.calls == 2
    assert output["status"] == RunStatus.SUCCEEDED.value
    assert output["node_results"][0]["attempts"] == 2


class RaisingRuntime(ComputeRuntime):
    async def invoke(self, request: InvocationRequest):
        raise RuntimeError(request.agent_name)

    def register(self, agent_name: str, handler) -> None:
        pass


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_emits_exactly_once_for_defensive_runtime_exception() -> None:
    set_compute_runtime(RaisingRuntime())
    events = collect_events()
    output = await OrchestratorAgent().invoke(request([node("n1", "raising")], max_retries=0))
    assert output["status"] == RunStatus.FAILED.value
    assert [event.detail_type for event in events].count("PlanNodeStarted") == 1
    assert [event.detail_type for event in events].count("PlanNodeCompleted") == 1
    assert [event.detail_type for event in events].count("RunCompleted") == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_cancellation_reaps_children_and_completes_every_node() -> None:
    runtime = get_compute_runtime()
    invoked = asyncio.Event()
    cleaned = asyncio.Event()

    async def slow(_request: InvocationRequest) -> dict[str, Any]:
        invoked.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    runtime.register("slow", slow)
    events = collect_events()
    task = asyncio.create_task(
        OrchestratorAgent().invoke(
            request([node("n1", "slow"), node("n2", "smoke", depends_on=["n1"])], run_id="r-cancel")
        )
    )
    await asyncio.wait_for(invoked.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(cleaned.wait(), timeout=1)
    values = await get_state_store().hgetall("run:r-cancel")
    assert values["status"] == RunStatus.CANCELLED.value
    assert [event.detail_type for event in events].count("RunCompleted") == 1
    terminal = next(event for event in events if event.detail_type == "RunCompleted")
    assert terminal.status == RunStatus.CANCELLED
    started = [event.node_id for event in events if event.detail_type == "PlanNodeStarted"]
    completed = [event for event in events if event.detail_type == "PlanNodeCompleted"]
    assert started == ["n1"]
    assert {event.node_id for event in completed} == {"n1", "n2"}
    assert len(completed) == 2
    assert {event.metadata.correlation_id for event in events} == {"r-cancel"}
