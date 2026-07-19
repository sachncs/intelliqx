"""IntelliqX service: ASGI app + embedded worker.

Single bearer-token auth, /healthz, /readyz, and /v1/runs endpoints
backed by a SQLite job queue and a single embedded worker process.
The worker reuses the existing :class:`intelliqx_compute.runtime` and
the Pydantic AI agent registry, so every server call exercises the
same code paths as a direct CLI invocation.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from intelliqx_compute.runtime import (
    InvocationRequest,
    InvocationResponse,
    get_compute_runtime,
    reset_compute_runtime,
)
from intelliqx_observability.logging import configure_logging, get_logger
from intelliqx_observability.tracing import get_tracer

from .auth import bearer_token_from_header
from .state import RunStatus, StateStore

log = get_logger(__name__)


class Settings:
    """Runtime configuration loaded from environment variables."""

    def __init__(self) -> None:
        self.token = os.environ.get("INTELLIQX_API_TOKEN", "dev-token-change-me")
        self.state_path = Path(os.environ.get("INTELLIQX_STATE_DB", ":memory:") or ":memory:")
        self.okf_path = os.environ.get("INTELLIQX_OKF_DB", ":memory:") or ":memory:"
        self.worker_count = int(os.environ.get("INTELLIQX_WORKERS", "1"))
        self.max_retries = int(os.environ.get("INTELLIQX_MAX_RETRIES", "1"))
        self.run_ttl_seconds = int(os.environ.get("INTELLIQX_RUN_TTL", "3600"))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    configure_logging(level="INFO", json_logs=True)
    state = StateStore(settings.state_path)
    app.state.settings = settings
    app.state.state = state
    app.state.tracer = get_tracer()
    app.state.worker_stop = asyncio.Event()
    app.state.worker_tasks = []
    try:
        from agents import register_all, register_compute_handlers
    except ImportError:  # pragma: no cover - agents workspace not available
        register_all = None  # type: ignore[assignment]
    if register_all is not None:
        register_all()
        register_compute_handlers()
    for _ in range(max(settings.worker_count, 1)):
        task = asyncio.create_task(_worker_loop(app))
        app.state.worker_tasks.append(task)
    log.info(
        "service_started", workers=len(app.state.worker_tasks), state_path=str(settings.state_path)
    )
    try:
        yield
    finally:
        app.state.worker_stop.set()
        for task in app.state.worker_tasks:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            for task in app.state.worker_tasks:
                await task
        reset_compute_runtime()
        state.close()
        log.info("service_stopped")


async def _worker_loop(app: FastAPI) -> None:
    state: StateStore = app.state.state
    settings: Settings = app.state.settings
    while not app.state.worker_stop.is_set():
        claimed = state.claim_next(settings.worker_count, settings.max_retries)
        if claimed is None:
            try:
                await asyncio.wait_for(app.state.worker_stop.wait(), timeout=0.5)
            except TimeoutError:
                continue
            else:
                break
            continue
        run_id, agent_name, input_payload, tenant_id, attempt = claimed
        log.info("run_picked_up", run_id=run_id, agent=agent_name, attempt=attempt)
        with app.state.tracer.span(f"run.{agent_name}") as span:
            span.set_attribute("run_id", run_id)
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("agent_name", agent_name)
            span.set_attribute("attempt", attempt)
            try:
                response: InvocationResponse = await get_compute_runtime().invoke(
                    InvocationRequest(
                        agent_name=agent_name,
                        input=input_payload,
                        tenant_id=tenant_id,
                        timeout_seconds=300,
                        metadata={"run_id": run_id, "attempt": attempt},
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("worker_runtime_exception", run_id=run_id)
                state.complete(
                    run_id, RunStatus.FAILED, error=f"{type(exc).__name__}: {exc}", duration_ms=0
                )
                continue
            if response.status == "ok":
                state.complete(
                    run_id,
                    RunStatus.SUCCEEDED,
                    output=response.output,
                    duration_ms=response.duration_ms,
                )
                log.info("run_succeeded", run_id=run_id, duration_ms=response.duration_ms)
            else:
                if attempt >= settings.max_retries:
                    state.complete(
                        run_id,
                        RunStatus.FAILED,
                        error=response.error or f"transport status {response.status}",
                        duration_ms=response.duration_ms,
                    )
                    log.warning(
                        "run_failed", run_id=run_id, status=response.status, attempts=attempt
                    )
                else:
                    state.requeue(run_id, attempt + 1)
                    log.info(
                        "run_requeued",
                        run_id=run_id,
                        status=response.status,
                        next_attempt=attempt + 1,
                    )


def require_token(request: Request) -> None:
    settings: Settings = request.app.state.settings
    token = bearer_token_from_header(request.headers.get("authorization"))
    if not hmac.compare_digest(token or "", settings.token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


def create_app() -> FastAPI:
    app = FastAPI(title="intelliqx", version="0.2.0", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        state: StateStore = app.state.state
        try:
            state.ping()
        except Exception as exc:  # pragma: no cover
            return JSONResponse(status_code=503, content={"status": "error", "error": str(exc)})
        return JSONResponse(content={"status": "ok"})

    @app.post("/v1/runs", dependencies=[Depends(require_token)])
    async def submit_run(request: Request) -> JSONResponse:
        body = await _read_json(request)
        agent_name = str(body.get("agent", "")).strip()
        tenant_id = str(body.get("tenant_id", "t1")).strip() or "t1"
        input_payload = body.get("input", {}) or {}
        if not agent_name:
            raise HTTPException(status_code=400, detail="agent is required")
        run_id = str(uuid.uuid4())
        app.state.state.enqueue(
            run_id=run_id, agent_name=agent_name, tenant_id=tenant_id, input_payload=input_payload
        )
        return JSONResponse(
            status_code=202, content={"run_id": run_id, "status": RunStatus.PENDING.value}
        )

    @app.get("/v1/runs/{run_id}", dependencies=[Depends(require_token)])
    async def get_run(run_id: str, request: Request) -> JSONResponse:
        record = request.app.state.state.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="run not found")
        return JSONResponse(content=record.as_dict())

    @app.delete("/v1/runs/{run_id}", dependencies=[Depends(require_token)])
    async def cancel_run(run_id: str, request: Request) -> JSONResponse:
        state: StateStore = request.app.state
        cancelled = state.cancel(run_id)
        if not cancelled:
            raise HTTPException(status_code=409, detail="run not in a cancellable state")
        return JSONResponse(content={"run_id": run_id, "status": RunStatus.CANCELLED.value})

    return app


async def _read_json(request: Request) -> dict[str, Any]:
    body = await request.body()
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="expected object body")
    return parsed


__all__ = ["Settings", "create_app", "lifespan"]
