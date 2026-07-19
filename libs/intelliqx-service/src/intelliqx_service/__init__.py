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

from intelliqx_service.app import Settings, create_app, lifespan
from intelliqx_service.auth import API_TOKEN_ENV, bearer_token_from_header
from intelliqx_service.state import RunRecord, RunStatus, StateStore

__all__ = [
    "API_TOKEN_ENV",
    "RunRecord",
    "RunStatus",
    "Settings",
    "StateStore",
    "bearer_token_from_header",
    "create_app",
    "lifespan",
]
