"""Modal compute adapter.

Invokes agents as ``modal.Function``s via ``.remote()`` (synchronous
HTTP-style call) or ``.spawn()`` (fire-and-forget). The runtime
expects each agent to be deployed as a Modal function in the same
app, named after the agent's registry key.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from intelliqx_compute.runtime import ComputeRuntime, InvocationRequest, InvocationResponse


class ModalComputeRuntime(ComputeRuntime):
    """Invokes agents via Modal Functions.

    Args:
        app_name: Modal app name. Defaults to ``"aqip"``.
    """

    def __init__(self, app_name: str = "aqip") -> None:
        self.app_name = app_name
        self._modal_app = None
        # agent_name -> modal.Function handle
        self._functions: dict[str, Any] = {}
        self._available = self._try_init()

    def _try_init(self) -> bool:
        try:
            import modal  # type: ignore

            self._modal_app = modal.App(self.app_name)
            return True
        except Exception:
            return False

    async def invoke(self, request: InvocationRequest) -> InvocationResponse:
        if not self._available or request.agent_name not in self._functions:
            return InvocationResponse(
                agent_name=request.agent_name,
                output={},
                duration_ms=0,
                status="not_found",
                error=f"No modal function registered for {request.agent_name}",
            )
        fn = self._functions[request.agent_name]
        start = time.monotonic()
        try:
            # ``.remote`` is blocking; offload to a thread.
            output = await asyncio.to_thread(fn.remote, request.model_dump(mode="json"))
            duration_ms = int((time.monotonic() - start) * 1000)
            return InvocationResponse(
                agent_name=request.agent_name,
                output=output,
                duration_ms=duration_ms,
                status="ok",
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return InvocationResponse(
                agent_name=request.agent_name,
                output={},
                duration_ms=duration_ms,
                status="error",
                error=str(e),
            )

    def register(self, agent_name: str, handler) -> None:
        """Register a Modal function as the implementation of ``agent_name``.

        Looks up the function by name in the Modal app. The function
        must already be deployed (``modal deploy``); this method
        does not provision it.
        """
        if not self._available:
            return
        import modal  # type: ignore

        # ``Function.from_name`` resolves a deployed function by
        # (app, function-name). ``create_if_missing`` is a
        # no-op for functions that already exist.
        fn = modal.Function.from_name(self.app_name, agent_name, create_if_missing=True)
        self._functions[agent_name] = fn
