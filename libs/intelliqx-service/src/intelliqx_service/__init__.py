"""IntelliqX hardened single-node service.

ASGI app + embedded worker; one container, one process, one bearer
auth token. The service exposes:

* ``GET /healthz`` — process liveness.
* ``GET /readyz`` — DB ping (returns 503 on failure).
* ``POST /v1/runs`` — enqueue a job; returns 202 + ``run_id``.
* ``GET /v1/runs/{id}`` — return the current record.
* ``DELETE /v1/runs/{id}`` — cancel a pending or running job.

Persistence is the embedded SQLite state store plus the OKF
``Index``; no external services are required.
"""

from __future__ import annotations

from intelliqx_service.app import (
    API_TOKEN_ENV,
    MAX_RETRIES_ENV,
    POLL_INTERVAL_SECONDS,
    STATE_DB_ENV,
    WORKER_COUNT_ENV,
    RunSubmission,
    Settings,
    create_app,
    lifespan,
    require_token,
)
from intelliqx_service.auth import BEARER_SCHEME, bearer_token_from_header
from intelliqx_service.state import (
    RunNotCancellableError,
    RunNotFoundError,
    RunRecord,
    RunStatus,
    StateStore,
)

__all__ = [
    "API_KEY_ENV",  # legacy alias placeholder; not exported
    "API_TOKEN_ENV",
    "BEARER_SCHEME",
    "MAX_RETRIES_ENV",
    "POLL_INTERVAL_SECONDS",
    "STATE_DB_ENV",
    "WORKER_COUNT_ENV",
    "RunNotCancellableError",
    "RunNotFoundError",
    "RunRecord",
    "RunStatus",
    "RunSubmission",
    "Settings",
    "StateStore",
    "bearer_token_from_header",
    "create_app",
    "lifespan",
    "require_token",
]
