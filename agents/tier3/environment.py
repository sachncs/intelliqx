"""Environment Agent (Tier 3).

Provisions an ephemeral test environment. In local/dev runs the
agent starts the in-process FastAPI "reference app" (a tiny
purpose-built HTTP service used by the Tier 3 tests). In
production the agent would call a cloud provisioning path
(ECS, Cloud Run, Terraform …) — that wiring is deliberately left
out of the scaffold.

The agent runs uvicorn in a **separate thread** rather than as an
asyncio task. The reason is uvicorn's startup path: when binding
fails, it calls ``sys.exit(STARTUP_FAILURE)`` which raises
:class:`SystemExit` from inside a task. The exception does not
propagate cleanly to the awaiting coroutine (asyncio "task
exception was never retrieved" warnings) and can deadlock the
event loop. Running uvicorn in a worker thread avoids both
problems.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import uvicorn
from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from pydantic import BaseModel, ConfigDict, Field


class EnvironmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_path: str | None = None  # path to a FastAPI app module
    port: int = 0  # 0 = pick free port
    health_path: str = "/health"
    timeout_seconds: int = 30
    tenant_id: str


class EnvironmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    base_url: str
    health: str
    ready: bool
    handle: dict[str, Any] = Field(default_factory=dict, exclude=True)


class EnvironmentAgent(AgentBase):
    META = AgentMeta(
        name="environment",
        tier=3,
        version="0.1.0",
        description="Provisions an ephemeral test environment.",
    )
    INPUT_MODEL = EnvironmentInput
    OUTPUT_MODEL = EnvironmentOutput

    @traced_agent("environment")
    async def run(self, ctx: AgentContext, input: EnvironmentInput) -> EnvironmentOutput:
        # Lazy imports keep ``aqip-agents`` importable on machines
        # without FastAPI installed (e.g. the Lambda Layer that
        # only runs the Orchestrator).
        import httpx

        from tests.fixtures.reference_app.app import app as ref_app

        port = input.port or _find_free_port()
        config = uvicorn.Config(ref_app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)

        # Run uvicorn in a daemon thread; see module docstring for
        # the SystemExit rationale.
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()

        # Poll the health endpoint until ready or until the
        # thread dies. The 100ms interval is short enough to
        # detect fast startups and long enough to avoid busy-
        # waiting the event loop.
        base_url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + input.timeout_seconds
        ready = False
        while time.monotonic() < deadline:
            if not server_thread.is_alive() and not ready:
                raise RuntimeError(
                    f"Environment server failed to start on {base_url} (thread exited)"
                )
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    r = await client.get(f"{base_url}{input.health_path}")
                if r.status_code == 200:
                    ready = True
                    break
            except Exception:
                # Connection refused while uvicorn is still
                # binding; just retry.
                pass
            await asyncio.sleep(0.1)

        if not ready:
            server.should_exit = True
            await asyncio.sleep(0.1)
            raise RuntimeError(f"Environment failed to become ready at {base_url}")

        return EnvironmentOutput(
            base_url=base_url,
            health=input.health_path,
            ready=True,
            handle={"port": port, "server": server, "thread": server_thread},
        )


def _find_free_port() -> int:
    """Return an OS-assigned free TCP port.

    Binding to port 0 lets the kernel pick; we read the assigned
    number back via ``getsockname``. The socket is closed before
    the function returns, so there's a small race with uvicorn
    reusing the port — acceptable for tests, not for production.
    """
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
