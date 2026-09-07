"""IntelliqX service: ASGI app + embedded worker.

Single bearer-token auth, /healthz, /readyz, and /v1/runs
endpoints backed by a SQLite job queue and a single embedded worker
process. The worker reuses the existing
:class:`intelliqx_compute.runtime` and the Pydantic AI agent
registry, so every server call exercises the same code paths as a
direct CLI invocation.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import os
import sqlite3
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
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
from intelliqx_observability.tracing import SpanProxy, get_tracer
from pydantic import BaseModel, ConfigDict, Field

from .auth import bearer_token_from_header
from .state import RunStatus, StateStore

log = get_logger(__name__)

API_TOKEN_ENV = "INTELLIQX_API_TOKEN"
STATE_DB_ENV = "INTELLIQX_STATE_DB"
WORKER_COUNT_ENV = "INTELLIQX_WORKERS"
MAX_RETRIES_ENV = "INTELLIQX_MAX_RETRIES"
RUN_TTL_ENV = "INTELLIQX_RUN_TTL"
POLL_INTERVAL_SECONDS = 0.5
INVOCATION_TIMEOUT_SECONDS = 300

DEFAULT_TOKEN = "dev-token-change-me"
DEFAULT_STATE_PATH = ":memory:"
DEFAULT_WORKER_COUNT = 1
DEFAULT_MAX_RETRIES = 1
DEFAULT_RUN_TTL_SECONDS = 3600


@dataclass(frozen=True)
class Settings:
    """Service configuration loaded from environment variables.

    Attributes:
        token: Bearer token required for every protected endpoint.
        state_path: SQLite path for the run queue (``:memory:`` for
            in-process tests).
        worker_count: Number of background worker coroutines.
        max_retries: Per-run retry budget for transport failures.
        run_ttl_seconds: Seconds after which an unused run state
            row can be evicted.
    """

    token: str
    state_path: Path
    worker_count: int
    max_retries: int
    run_ttl_seconds: int

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        """Build a :class:`Settings` from ``os.environ`` (or a test mapping)."""
        src = env if env is not None else os.environ
        return cls(
            token=src.get(API_TOKEN_ENV, DEFAULT_TOKEN),
            state_path=Path(src.get(STATE_DB_ENV) or DEFAULT_STATE_PATH),
            worker_count=_parse_int(src.get(WORKER_COUNT_ENV), DEFAULT_WORKER_COUNT),
            max_retries=_parse_int(src.get(MAX_RETRIES_ENV), DEFAULT_MAX_RETRIES),
            run_ttl_seconds=_parse_int(src.get(RUN_TTL_ENV), DEFAULT_RUN_TTL_SECONDS),
        )


def _parse_int(raw: str | None, default: int) -> int:
    """Parse a positive integer env value, falling back to ``default``."""
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"expected integer, got {raw!r}") from exc


def require_token(request: Request) -> None:
    """Validate the bearer token on every protected request."""
    settings: Settings = request.app.state.settings
    presented = bearer_token_from_header(request.headers.get("authorization"))
    expected = settings.token.encode("utf-8")
    if presented is None or not hmac.compare_digest(presented.encode("utf-8"), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing token"
        )


async def _read_json_object(request: Request) -> dict[str, Any]:
    """Parse the request body as a JSON object, raising 400 on failure."""
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


def _register_agents() -> None:
    """Register the Pydantic AI roles with the compute runtime.

    Falls back silently when the ``agents`` workspace is not
    installed (for example, in a slim image). Production always
    ships with the agents workspace.
    """
    try:
        from agents import register_compute_handlers
    except ImportError:  # pragma: no cover - agents workspace absent
        log.warning("agents_workspace_missing")
        return
    register_compute_handlers()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage service-wide state for the lifetime of the ASGI app."""
    settings = Settings.from_env()
    configure_logging(level="INFO", json_logs=True)
    state = StateStore(settings.state_path, run_ttl_seconds=settings.run_ttl_seconds)
    app.state.settings = settings
    app.state.state = state
    app.state.tracer = get_tracer()
    app.state.worker_stop = asyncio.Event()
    app.state.worker_tasks = []

    _register_agents()
    for _ in range(max(settings.worker_count, 1)):
        app.state.worker_tasks.append(asyncio.create_task(_worker_loop(app)))
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
    """Drain the run queue forever, until the stop event is set."""
    state: StateStore = app.state.state
    settings: Settings = app.state.settings
    while not app.state.worker_stop.is_set():
        claimed = state.claim_next()
        if claimed is None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(app.state.worker_stop.wait(), timeout=POLL_INTERVAL_SECONDS)
            continue
        await _process_claim(app, state, settings, claimed)


async def _process_claim(
    app: FastAPI,
    state: StateStore,
    settings: Settings,
    claimed: tuple[str, str, dict[str, Any], str, int],
) -> None:
    """Process one claimed run: invoke the agent and record the result."""
    run_id, agent_name, input_payload, tenant_id, attempt = claimed
    log.info("run_picked_up", run_id=run_id, agent=agent_name, attempt=attempt)
    with app.state.tracer.span(f"run.{agent_name}") as span:
        _tag_run_span(span, run_id, tenant_id, agent_name, attempt)
        try:
            response = await get_compute_runtime().invoke(
                _build_invocation_request(run_id, agent_name, tenant_id, input_payload, attempt)
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("worker_runtime_exception", run_id=run_id)
            state.complete(
                run_id, RunStatus.FAILED, error=f"{type(exc).__name__}: {exc}", duration_ms=0
            )
            return
        _record_outcome(state, run_id, response, settings, attempt)


def _tag_run_span(
    span: SpanProxy, run_id: str, tenant_id: str, agent_name: str, attempt: int
) -> None:
    span.set_attribute("run_id", run_id)
    span.set_attribute("tenant_id", tenant_id)
    span.set_attribute("agent_name", agent_name)
    span.set_attribute("attempt", attempt)


def _build_invocation_request(
    run_id: str, agent_name: str, tenant_id: str, input_payload: dict[str, Any], attempt: int
) -> InvocationRequest:
    return InvocationRequest(
        agent_name=agent_name,
        input=input_payload,
        tenant_id=tenant_id,
        timeout_seconds=INVOCATION_TIMEOUT_SECONDS,
        metadata={"run_id": run_id, "attempt": attempt},
    )


def _record_outcome(
    state: StateStore, run_id: str, response: InvocationResponse, settings: Settings, attempt: int
) -> None:
    """Persist the terminal state for one run."""
    if response.status == "ok":
        state.complete(
            run_id, RunStatus.SUCCEEDED, output=response.output, duration_ms=response.duration_ms
        )
        log.info("run_succeeded", run_id=run_id, duration_ms=response.duration_ms)
        return
    if attempt >= settings.max_retries:
        state.complete(
            run_id,
            RunStatus.FAILED,
            error=response.error or f"transport status {response.status}",
            duration_ms=response.duration_ms,
        )
        log.warning("run_failed", run_id=run_id, status=response.status, attempts=attempt)
        return
    state.requeue(run_id, attempt + 1)
    log.info("run_requeued", run_id=run_id, status=response.status, next_attempt=attempt + 1)


def create_app() -> FastAPI:
    """Build the FastAPI application with the production routes."""
    app = FastAPI(title="intelliqx", version="0.2.0", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        try:
            request.app.state.state.ping()
        except sqlite3.Error as exc:
            return JSONResponse(status_code=503, content={"status": "error", "error": str(exc)})
        return JSONResponse(content={"status": "ok"})

    @app.post("/v1/runs", dependencies=[Depends(require_token)])
    async def submit_run(request: Request) -> JSONResponse:
        body = await _read_json_object(request)
        run_request = RunSubmission.model_validate(body)
        run_id = str(uuid.uuid4())
        request.app.state.state.enqueue(
            run_id=run_id,
            agent_name=run_request.agent,
            tenant_id=run_request.tenant_id,
            input_payload=run_request.input,
        )
        log.info(
            "run_enqueued", run_id=run_id, agent=run_request.agent, tenant_id=run_request.tenant_id
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
        cancelled = request.app.state.state.cancel(run_id)
        if not cancelled:
            raise HTTPException(status_code=409, detail="run not in a cancellable state")
        log.info("run_cancelled", run_id=run_id)
        return JSONResponse(content={"run_id": run_id, "status": RunStatus.CANCELLED.value})

    return app


class RunSubmission(BaseModel):
    """Validated body for ``POST /v1/runs``.

    Attributes:
        agent: Required Pydantic AI role name to invoke.
        tenant_id: Optional tenant id; defaults to ``"t1"``.
        input: Free-form dict passed straight to the agent.
    """

    model_config = ConfigDict(extra="forbid")

    agent: str = Field(min_length=1)
    tenant_id: str = "t1"
    input: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "API_TOKEN_ENV",
    "MAX_RETRIES_ENV",
    "POLL_INTERVAL_SECONDS",
    "STATE_DB_ENV",
    "WORKER_COUNT_ENV",
    "RunSubmission",
    "Settings",
    "create_app",
    "lifespan",
    "require_token",
]
