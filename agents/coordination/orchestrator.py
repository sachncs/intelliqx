"""Deterministic lifecycle orchestration for plan DAGs."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any, Literal, cast

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_compute.runtime import InvocationRequest, get_compute_runtime
from intelliqx_core.models import AgentCategory, DomainOutcome, PlanNode, RunStatus
from intelliqx_events.bus import get_event_bus
from intelliqx_state.store import get_state_store
from pydantic import BaseModel, ConfigDict, Field, model_validator

type TransportStatus = Literal["ok", "timeout", "error", "not_found", "not_invoked"]
TRANSPORT_STATUSES = frozenset({"ok", "timeout", "error", "not_found"})
RETRYABLE_STATUSES = frozenset({"timeout", "error"})
RUN_TTL_SECONDS = 3600


class OrchestratorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    goal_id: str
    nodes: list[PlanNode] = Field(min_length=1)
    tenant_id: str
    run_id: str
    max_parallel: int = Field(default=4, ge=1, le=64)
    max_retries: int = Field(default=2, ge=0, le=5)

    @model_validator(mode="after")
    def validate_plan(self) -> OrchestratorInput:
        seen: set[str] = set()
        for node in self.nodes:
            if node.node_id in seen:
                raise ValueError(f"Duplicate node_id {node.node_id!r}")
            seen.add(node.node_id)
        for node in self.nodes:
            for dependency in node.depends_on:
                if dependency == node.node_id:
                    raise ValueError(f"Node {node.node_id!r} cannot depend on itself")
                if dependency not in seen:
                    raise ValueError(
                        f"Node {node.node_id!r} depends on unknown node {dependency!r}"
                    )
        indegree = {node.node_id: len(node.depends_on) for node in self.nodes}
        dependants: dict[str, list[str]] = {node.node_id: [] for node in self.nodes}
        for node in self.nodes:
            for dependency in node.depends_on:
                dependants[dependency].append(node.node_id)
        ready = deque(node_id for node_id, degree in indegree.items() if degree == 0)
        visited = 0
        while ready:
            node_id = ready.popleft()
            visited += 1
            for dependant in dependants[node_id]:
                indegree[dependant] -= 1
                if indegree[dependant] == 0:
                    ready.append(dependant)
        if visited != len(self.nodes):
            raise ValueError("Plan contains a cycle")
        return self


class NodeResult(BaseModel):
    """Transport and domain result of one plan node."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    agent: str
    status: TransportStatus
    outcome: DomainOutcome
    duration_ms: int = 0
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    attempts: int = Field(default=0, ge=0, le=6)


class OrchestratorOutput(BaseModel):
    """Final run result with node results in plan order."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    plan_id: str
    status: RunStatus
    node_results: list[NodeResult] = Field(default_factory=list)
    duration_ms: int = 0


class OrchestratorAgent(AgentBase[OrchestratorInput, OrchestratorOutput]):
    """Runs a validated DAG with bounded parallelism and transport retries."""

    META = AgentMeta(
        name="orchestrator",
        category=AgentCategory.COORDINATION,
        version="0.1.0",
        description="Executes a plan DAG, handling retries, parallelism, and audit.",
    )
    INPUT_MODEL = OrchestratorInput
    OUTPUT_MODEL = OrchestratorOutput

    @traced_agent("orchestrator")
    async def run(self, ctx: AgentContext, input: OrchestratorInput) -> OrchestratorOutput:
        if input.tenant_id != ctx.tenant.tenant_id:
            raise ValueError("Orchestrator tenant_id does not match invocation tenant")

        from agents.coordination.events import (
            PlanNodeCompleted,
            PlanNodeStarted,
            RunCompleted,
            RunStarted,
            make_metadata,
        )

        bus = get_event_bus()
        state = get_state_store()
        runtime = get_compute_runtime()
        tenant_id = input.tenant_id
        run_key = f"run:{input.run_id}"
        started_at = datetime.now(UTC)
        started = time.monotonic()
        logger = self.logger.bind(run_id=input.run_id, plan_id=input.plan_id)
        node_map = {node.node_id: node for node in input.nodes}
        plan_index = {node.node_id: index for index, node in enumerate(input.nodes)}
        dependants: dict[str, list[str]] = {node.node_id: [] for node in input.nodes}
        remaining = {node.node_id: len(node.depends_on) for node in input.nodes}
        for node in input.nodes:
            for dependency in node.depends_on:
                dependants[dependency].append(node.node_id)
        ready = deque(node.node_id for node in input.nodes if not node.depends_on)
        results: dict[str, NodeResult] = {}
        tasks: dict[asyncio.Task[NodeResult], str] = {}
        started_events: set[str] = set()
        completed_events: set[str] = set()
        terminal_emitted = False

        def metadata():
            return make_metadata(
                tenant_id=tenant_id, produced_by="orchestrator", correlation_id=input.run_id
            )

        async def persist(status: RunStatus, summary: dict[str, int] | None = None) -> None:
            values = {
                "status": status.value,
                "plan_id": input.plan_id,
                "goal_id": input.goal_id,
                "started_at": started_at.isoformat(),
            }
            if status != RunStatus.RUNNING:
                values["completed_at"] = datetime.now(UTC).isoformat()
            if summary is not None:
                values["summary"] = json.dumps(summary, sort_keys=True, separators=(",", ":"))
            for field, value in values.items():
                await state.hset(run_key, field, value)
            await state.expire(run_key, RUN_TTL_SECONDS)

        async def emit_node_completed(result: NodeResult) -> None:
            if result.node_id in completed_events:
                return
            completed_events.add(result.node_id)
            await bus.publish(
                "plan.node.completed",
                PlanNodeCompleted(
                    metadata=metadata(),
                    plan_id=input.plan_id,
                    node_id=result.node_id,
                    agent=result.agent,
                    status=result.status,
                    outcome=result.outcome,
                    attempts=result.attempts,
                    duration_ms=result.duration_ms,
                    output=result.output,
                    error=result.error,
                ),
            )

        async def emit_terminal(status: RunStatus, summary: dict[str, int]) -> None:
            nonlocal terminal_emitted
            if terminal_emitted:
                return
            terminal_emitted = True
            await bus.publish(
                "run.completed",
                RunCompleted(
                    metadata=metadata(),
                    run_id=input.run_id,
                    plan_id=input.plan_id,
                    goal_id=input.goal_id,
                    status=status,
                    summary=summary,
                ),
            )

        async def invoke_node(node: PlanNode) -> NodeResult:
            node_logger = logger.bind(node_id=node.node_id, agent=node.agent)
            attempts = 0
            last_status: TransportStatus = "error"
            last_output: dict[str, Any] = {}
            last_error: str | None = None
            last_duration_ms = 0
            started_events.add(node.node_id)
            try:
                await bus.publish(
                    "plan.node.started",
                    PlanNodeStarted(
                        metadata=metadata(),
                        plan_id=input.plan_id,
                        node_id=node.node_id,
                        agent=node.agent,
                    ),
                )
                while attempts <= input.max_retries:
                    attempts += 1
                    attempt_started = time.monotonic()
                    try:
                        response = await runtime.invoke(
                            InvocationRequest(
                                agent_name=node.agent,
                                input=node.inputs,
                                tenant_id=tenant_id,
                                timeout_seconds=node.timeout_seconds,
                                metadata={
                                    "run_id": input.run_id,
                                    "plan_id": input.plan_id,
                                    "node_id": node.node_id,
                                },
                            )
                        )
                        if response.status in TRANSPORT_STATUSES:
                            last_status = cast(TransportStatus, response.status)
                            last_error = response.error
                        else:
                            last_status = "error"
                            last_error = f"Unknown transport status {response.status!r}"
                        last_output = response.output
                        last_duration_ms = response.duration_ms
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        last_status = "error"
                        last_output = {}
                        last_error = f"{type(error).__name__}: {error}"
                        last_duration_ms = int((time.monotonic() - attempt_started) * 1000)
                    if last_status not in RETRYABLE_STATUSES or attempts > input.max_retries:
                        break
                    node_logger.warning(
                        "orchestrator_node_retry", attempt=attempts, transport_status=last_status
                    )
                    await asyncio.sleep(min(2**attempts * 0.05, 1.0))
                if last_status == "ok":
                    raw_outcome = last_output.get("outcome", "passed")
                    if raw_outcome in {"passed", "failed", "blocked"}:
                        outcome = cast(DomainOutcome, raw_outcome)
                    else:
                        outcome = "failed"
                        last_error = f"Invalid domain outcome {raw_outcome!r}"
                else:
                    outcome = "failed"
                result = NodeResult(
                    node_id=node.node_id,
                    agent=node.agent,
                    status=last_status,
                    outcome=outcome,
                    duration_ms=last_duration_ms,
                    output=last_output,
                    error=last_error,
                    attempts=attempts,
                )
            except asyncio.CancelledError:
                node_logger.warning("orchestrator_node_cancelled", attempts=attempts)
                result = NodeResult(
                    node_id=node.node_id,
                    agent=node.agent,
                    status="error",
                    outcome="failed",
                    duration_ms=last_duration_ms,
                    error="Invocation cancelled",
                    attempts=attempts,
                )
            except Exception:
                node_logger.exception("orchestrator_node_exception")
                result = NodeResult(
                    node_id=node.node_id,
                    agent=node.agent,
                    status="error",
                    outcome="failed",
                    duration_ms=last_duration_ms,
                    error="Orchestrator node execution failed",
                    attempts=attempts,
                )
            await emit_node_completed(result)
            if result.outcome != "passed":
                node_logger.error(
                    "orchestrator_node_failed",
                    transport_status=result.status,
                    outcome=result.outcome,
                    attempts=result.attempts,
                )
            return result

        async def block_node(node: PlanNode, prerequisites: list[str]) -> NodeResult:
            result = NodeResult(
                node_id=node.node_id,
                agent=node.agent,
                status="not_invoked",
                outcome="blocked",
                error=f"Blocked by prerequisites: {', '.join(prerequisites)}",
                attempts=0,
            )
            logger.bind(node_id=node.node_id, agent=node.agent).warning(
                "orchestrator_node_blocked", prerequisites=prerequisites
            )
            await emit_node_completed(result)
            return result

        async def record_result(result: NodeResult) -> None:
            if result.node_id in results:
                return
            results[result.node_id] = result
            settled = deque([result.node_id])
            while settled:
                node_id = settled.popleft()
                for dependant_id in dependants[node_id]:
                    remaining[dependant_id] -= 1
                    if remaining[dependant_id] != 0:
                        continue
                    dependant = node_map[dependant_id]
                    prerequisites = [
                        dependency
                        for dependency in dependant.depends_on
                        if results[dependency].outcome != "passed"
                    ]
                    if prerequisites:
                        blocked = await block_node(dependant, prerequisites)
                        results[dependant_id] = blocked
                        settled.append(dependant_id)
                    else:
                        ready.append(dependant_id)

        async def schedule() -> None:
            while len(results) < len(input.nodes):
                while ready and len(tasks) < input.max_parallel:
                    node_id = ready.popleft()
                    task = asyncio.create_task(invoke_node(node_map[node_id]))
                    tasks[task] = node_id
                if not tasks:
                    break
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in sorted(done, key=lambda item: plan_index[tasks[item]]):
                    node_id = tasks.pop(task)
                    try:
                        result = task.result()
                    except Exception:
                        logger.bind(node_id=node_id, agent=node_map[node_id].agent).exception(
                            "orchestrator_task_exception"
                        )
                        result = NodeResult(
                            node_id=node_id,
                            agent=node_map[node_id].agent,
                            status="error",
                            outcome="failed",
                            error="Orchestrator task failed",
                            attempts=0,
                        )
                        await emit_node_completed(result)
                    await record_result(result)

        async def cancel_children() -> None:
            task_items = list(tasks.items())
            for task, _ in task_items:
                task.cancel()
            gathered = await asyncio.gather(
                *(task for task, _ in task_items), return_exceptions=True
            )
            for (_, node_id), item in zip(task_items, gathered, strict=True):
                if isinstance(item, NodeResult):
                    results.setdefault(node_id, item)
            for node in input.nodes:
                if node.node_id in results:
                    continue
                invoked = node.node_id in started_events
                result = NodeResult(
                    node_id=node.node_id,
                    agent=node.agent,
                    status="error" if invoked else "not_invoked",
                    outcome="failed" if invoked else "blocked",
                    error="Invocation cancelled" if invoked else "Run cancelled before invocation",
                    attempts=0,
                )
                await emit_node_completed(result)
                results[node.node_id] = result

        def ordered_results() -> list[NodeResult]:
            return [results[node.node_id] for node in input.nodes]

        def summarize() -> dict[str, int]:
            ordered = ordered_results()
            return {
                "passed": sum(result.outcome == "passed" for result in ordered),
                "failed": sum(result.outcome == "failed" for result in ordered),
                "blocked": sum(result.outcome == "blocked" for result in ordered),
                "total": len(ordered),
            }

        try:
            await persist(RunStatus.RUNNING)
            await bus.publish(
                "run.started",
                RunStarted(
                    metadata=metadata(),
                    run_id=input.run_id,
                    plan_id=input.plan_id,
                    goal_id=input.goal_id,
                ),
            )
            await schedule()
            summary = summarize()
            status = (
                RunStatus.SUCCEEDED
                if all(result.outcome == "passed" for result in ordered_results())
                else RunStatus.FAILED
            )
            await persist(status, summary)
            await emit_terminal(status, summary)
        except asyncio.CancelledError:
            logger.warning("orchestrator_run_cancelled", completed_nodes=len(results))
            await cancel_children()
            summary = summarize()
            await persist(RunStatus.CANCELLED, summary)
            await emit_terminal(RunStatus.CANCELLED, summary)
            raise

        return OrchestratorOutput(
            run_id=input.run_id,
            plan_id=input.plan_id,
            status=status,
            node_results=ordered_results(),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
