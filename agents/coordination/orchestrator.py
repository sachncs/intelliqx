"""Orchestrator Agent (Coordination).

Coordinates execution of a plan: invokes agents via the compute
runtime in dependency order, retries on failure with exponential
backoff, persists run status, emits events.

This module implements the in-process equivalent of a Step Functions
state machine. In production (AWS), the same Python logic is run by
a Step Functions Express workflow using ``asl.json`` (see
``workflows/orchestrator.asl.json``).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_compute.runtime import InvocationRequest, get_compute_runtime
from intelliqx_core.models import AgentCategory, RunStatus
from intelliqx_events.bus import get_event_bus
from intelliqx_state.store import get_state_store
from pydantic import BaseModel, ConfigDict, Field


class OrchestratorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    goal_id: str
    nodes: list[dict[str, Any]]
    tenant_id: str
    run_id: str
    max_parallel: int = 4
    max_retries: int = 2


class NodeResult(BaseModel):
    """Result of a single plan-node invocation.

    Attributes:
        node_id: Identifier of the plan node.
        agent: Agent name that was invoked.
        status: One of ``"ok"``, ``"error"``, ``"not_found"`` (see
            :class:`~intelliqx_compute.runtime.InvocationResponse.status`).
        duration_ms: Wall-clock duration of the (last) invocation.
        output: Serialised agent output. ``{}`` on failure.
        error: Error message if ``status != "ok"``; ``None`` on success.
        attempts: Total invocation attempts (initial + retries).
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    agent: str
    status: str
    duration_ms: int = 0
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    attempts: int = 1


class OrchestratorOutput(BaseModel):
    """Output payload for the Orchestrator.

    Attributes:
        run_id: Echoed from the input.
        plan_id: Echoed from the input.
        status: Overall run status — :attr:`RunStatus.SUCCEEDED` if
            every node returned ``"ok"``, otherwise :attr:`RunStatus.FAILED`.
        node_results: One :class:`NodeResult` per node, in the order
            the nodes completed.
        duration_ms: Total wall-clock duration of the run.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    plan_id: str
    status: RunStatus
    node_results: list[NodeResult] = Field(default_factory=list)
    duration_ms: int = 0


class OrchestratorAgent(AgentBase[OrchestratorInput, OrchestratorOutput]):
    """Coordinates a plan's execution.

    Algorithm:
        1. Build the DAG adjacency (``adj``, ``indegree``) and the
           set of ready nodes (those with ``indegree == 0``).
        2. Schedule ready nodes up to ``max_parallel`` concurrently.
        3. As each node completes, decrement the indegree of its
           dependents; any that drop to zero become ready.
        4. On failure, retry the node up to ``max_retries`` times
           with exponential backoff (capped at 1s).
        5. Persist the final status to the state store and emit
           ``run.completed``.

    A node is "failed" if it produced a non-``"ok"``
    :class:`InvocationResponse` after exhausting its retries. The
    orchestrator does **not** abort the rest of the plan on a single
    node failure (the planner would have caught real errors via
    tests); failed nodes are reported and the run is marked
    :attr:`RunStatus.FAILED` if at least one node failed.

    Thread-safety: a single orchestrator instance can run multiple
    plans in parallel because every piece of mutable state lives in
    locals of :meth:`run`.
    """

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
        bus = get_event_bus()
        state = get_state_store()
        runtime = get_compute_runtime()

        from agents.coordination.events import (
            PlanNodeCompleted,
            PlanNodeStarted,
            RunCompleted,
            RunStarted,
            make_metadata,
        )

        tenant_id = ctx.tenant.tenant_id
        metadata = make_metadata(tenant_id=tenant_id, produced_by="orchestrator")

        # Announce the run and persist the initial PENDING state.
        # The state-store key pattern is ``run:{run_id}``; we
        # also stash the plan_id in a hash for later lookup.
        await bus.publish(
            "run.started",
            RunStarted(
                metadata=metadata, run_id=input.run_id, plan_id=input.plan_id, goal_id=input.goal_id
            ),
        )
        await state.set(f"run:{input.run_id}", b"PENDING", ttl_seconds=3600)
        await state.hset(f"run:{input.run_id}", "plan_id", input.plan_id)

        start = time.monotonic()
        node_results: list[NodeResult] = []
        all_ok = True

        # Build adjacency for topological execution.
        ready: list[str] = []
        completed: set[str] = set()
        in_flight: set[str] = set()
        node_map: dict[str, dict[str, Any]] = {n["node_id"]: n for n in input.nodes}
        indegree: dict[str, int] = {}
        adj: dict[str, list[str]] = {nid: [] for nid in node_map}
        for n in input.nodes:
            indegree[n["node_id"]] = len(n.get("depends_on", []))
            for d in n.get("depends_on", []):
                adj[d].append(n["node_id"])

        for nid, deg in indegree.items():
            if deg == 0:
                ready.append(nid)

        async def invoke_node(nid: str) -> NodeResult:
            """Invoke one node, retrying on failure with backoff."""
            node = node_map[nid]
            agent_name = node["agent"]
            await bus.publish(
                "plan.node.started",
                PlanNodeStarted(
                    metadata=metadata, plan_id=input.plan_id, node_id=nid, agent=agent_name
                ),
            )
            attempts = 0
            last_err: str | None = None
            last_status = "error"
            last_output: dict[str, Any] = {}
            last_duration_ms = 0
            # The loop body runs at most ``max_retries + 1`` times
            # (initial attempt + each retry).
            while attempts <= input.max_retries:
                attempts += 1
                resp = await runtime.invoke(
                    InvocationRequest(
                        agent_name=agent_name,
                        input=node.get("inputs", {}),
                        tenant_id=tenant_id,
                        timeout_seconds=int(node.get("timeout_seconds", 300)),
                        metadata={"run_id": input.run_id, "plan_id": input.plan_id, "node_id": nid},
                    )
                )
                last_duration_ms = resp.duration_ms
                last_status = resp.status
                last_output = resp.output
                last_err = resp.error
                if resp.status == "ok":
                    break
                # Exponential backoff. Capped at 1s to keep the
                # overall run time bounded.
                if attempts <= input.max_retries:
                    await asyncio.sleep(min(2**attempts * 0.05, 1.0))
            result = NodeResult(
                node_id=nid,
                agent=agent_name,
                status=last_status,
                duration_ms=last_duration_ms,
                output=last_output,
                error=last_err,
                attempts=attempts,
            )
            await bus.publish(
                "plan.node.completed",
                PlanNodeCompleted(
                    metadata=metadata,
                    plan_id=input.plan_id,
                    node_id=nid,
                    agent=agent_name,
                    status=last_status,
                    duration_ms=last_duration_ms,
                    output=last_output,
                    error=last_err,
                ),
            )
            return result

        # node_futures lets the outer scheduler reap any straggling
        # tasks before returning.
        node_futures: dict[str, asyncio.Task[None]] = {}

        async def run_node(nid: str) -> None:
            """Wrap invoke_node so we can track in_flight + completed
            atomically and update the running totals.

            The body is structured to mutate ``all_ok`` and
            ``node_results`` only inside the ``try`` block (before
            the ``finally``), so a crash in the inner handler cannot
            leave the orchestrator in an inconsistent state.
            """
            nonlocal all_ok
            try:
                res = await invoke_node(nid)
            except Exception as e:
                # Defensive: invoke_node should not raise (it
                # converts every exception into an error response),
                # but if it does we still want a structured result.
                res = NodeResult(
                    node_id=nid, agent=node_map[nid]["agent"], status="error", error=str(e)
                )
            node_results.append(res)
            if res.status != "ok":
                all_ok = False
            in_flight.discard(nid)
            completed.add(nid)
            # Unlock any dependents whose last prerequisite just
            # completed.
            for nxt in adj[nid]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0 and nxt not in completed and nxt not in in_flight:
                    ready.append(nxt)

        async def run_until_done() -> None:
            """Main scheduling loop. Spawns up to ``max_parallel``
            tasks and waits for them to drain.
            """
            while True:
                # Schedule ready nodes up to the parallelism cap.
                while ready and len(in_flight) < input.max_parallel:
                    nid = ready.pop(0)
                    in_flight.add(nid)
                    task = asyncio.create_task(run_node(nid))
                    node_futures[nid] = task

                if not in_flight:
                    break
                # Short sleep yields to the event loop so the
                # in-flight tasks make progress.
                await asyncio.sleep(0.01)

        await run_until_done()

        # Reap any straggling tasks (defensive — they should have
        # completed inside ``run_until_done``).
        if node_futures:
            await asyncio.gather(*node_futures.values(), return_exceptions=True)

        duration_ms = int((time.monotonic() - start) * 1000)
        status = RunStatus.SUCCEEDED if all_ok else RunStatus.FAILED
        summary = {
            "ok": sum(1 for r in node_results if r.status == "ok"),
            "failed": sum(1 for r in node_results if r.status != "ok"),
            "total": len(node_results),
        }
        # Persist the final status; the RunCompleted event carries
        # the per-node summary.
        await state.set(f"run:{input.run_id}", status.value.encode("utf-8"), ttl_seconds=3600)
        await bus.publish(
            "run.completed",
            RunCompleted(
                metadata=metadata,
                run_id=input.run_id,
                plan_id=input.plan_id,
                goal_id=input.goal_id,
                status=status,
                summary=summary,
            ),
        )
        return OrchestratorOutput(
            run_id=input.run_id,
            plan_id=input.plan_id,
            status=status,
            node_results=node_results,
            duration_ms=duration_ms,
        )
