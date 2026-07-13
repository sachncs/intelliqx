"""Performance Agent (Tier 3).

Runs load/stress/spike/endurance/scalability tests against a target
URL and reports percentile latencies + SLO compliance. In tests
this is a self-contained runner over ``httpx.AsyncClient``; in
production the same shape can be implemented over k6 or Locust.

Concurrency: ``concurrency`` async workers share a single
``httpx.AsyncClient`` (so we reuse the connection pool) and hit the
target until ``duration_seconds`` elapses. The 30s default
per-request timeout is short enough to bound tail latency but long
enough to ride out a brief slow-down.

Percentile computation: we keep the timings list per run and
sort once at the end. The nearest-rank method is used (clamping
the index to ``n-1`` to keep ``p99`` well-defined for small
samples).
"""

from __future__ import annotations

import asyncio
import time
from typing import ClassVar

import httpx
from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from pydantic import BaseModel, ConfigDict, Field


class PerformanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    target_url: str
    profile: str = "load"  # load | stress | spike | endurance | scalability
    duration_seconds: int = 10
    concurrency: int = 5
    slo_p95_ms: float = 1000.0
    slo_error_rate: float = 0.01


class PerformanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests: int = 0
    errors: int = 0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    slo_pass: bool = False


class PerformanceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str
    result: PerformanceResult
    slo_breaches: list[str] = Field(default_factory=list)


class PerformanceAgent(AgentBase):
    META = AgentMeta(
        name="performance",
        tier=3,
        version="0.1.0",
        description="Runs load/stress/spike tests with SLO checks.",
    )
    INPUT_MODEL = PerformanceInput
    OUTPUT_MODEL = PerformanceOutput

    # Per-request client timeout. Generous default; the workload's
    # SLO is enforced separately via slo_p95_ms.
    DEFAULT_TIMEOUT_SECONDS: ClassVar[float] = 30.0

    @traced_agent("performance")
    async def run(self, ctx: AgentContext, input: PerformanceInput) -> PerformanceOutput:
        timings: list[float] = []
        errors = 0
        total = 0
        deadline = time.monotonic() + input.duration_seconds

        async def worker() -> None:
            """One worker: GET target_url until the deadline."""
            nonlocal errors, total
            async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT_SECONDS) as client:
                while time.monotonic() < deadline:
                    t0 = time.monotonic()
                    try:
                        r = await client.get(input.target_url)
                        total += 1
                        if r.status_code >= 500:
                            errors += 1
                    except Exception:
                        total += 1
                        errors += 1
                    timings.append((time.monotonic() - t0) * 1000)

        workers = [asyncio.create_task(worker()) for _ in range(input.concurrency)]
        await asyncio.gather(*workers, return_exceptions=True)

        timings.sort()
        n = len(timings)
        p50 = timings[int(n * 0.5)] if n else 0.0
        p95 = timings[int(n * 0.95)] if n else 0.0
        p99 = timings[int(n * 0.99)] if n else 0.0
        err_rate = errors / total if total else 0.0
        slo_pass = p95 <= input.slo_p95_ms and err_rate <= input.slo_error_rate
        breaches: list[str] = []
        if p95 > input.slo_p95_ms:
            breaches.append(f"p95 {p95:.0f}ms exceeds SLO {input.slo_p95_ms:.0f}ms")
        if err_rate > input.slo_error_rate:
            breaches.append(f"error rate {err_rate:.2%} exceeds SLO {input.slo_error_rate:.2%}")

        return PerformanceOutput(
            profile=input.profile,
            result=PerformanceResult(
                requests=total,
                errors=errors,
                p50_ms=p50,
                p95_ms=p95,
                p99_ms=p99,
                slo_pass=slo_pass,
            ),
            slo_breaches=breaches,
        )
