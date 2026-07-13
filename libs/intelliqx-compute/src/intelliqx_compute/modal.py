"""Modal compute adapter.

Invokes agents as ``modal.Function``s via ``.remote()`` (synchronous
HTTP-style call) or ``.spawn()`` (fire-and-forget). The runtime
expects each agent to be deployed as a Modal function in the same
app, named after the agent's registry key.

Error handling pattern (``_try_init`` / ``_available``):

* ``_try_init`` catches ``(ImportError, OSError)``. ``ImportError``
  covers the absence of the ``modal`` SDK. ``OSError`` covers
  failures when constructing the ``modal.App`` handle (e.g. an
  invalid ``MODAL_TOKEN_ID`` or a network error reaching the Modal
  API).
* When ``_try_init`` returns ``False``, ``invoke`` returns an
  ``InvocationResponse`` with ``status="not_found"`` and a
  descriptive error. This is **graceful degradation** — Modal-less
  CI and local dev keep working for the rest of the platform.
* When ``_try_init`` returns ``True`` but a specific agent function
  is not registered, ``invoke`` also returns ``status="not_found"``.
  When the Modal remote call itself fails, the exception is caught
  and returned as ``status="error"`` so the orchestration loop
  survives transient failures.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from intelliqx_compute.runtime import ComputeRuntime, InvocationRequest, InvocationResponse


class ModalComputeRuntime(ComputeRuntime):
    """Invokes agents via Modal Functions.

    Args:
        app_name: Modal app name. Defaults to ``"intelliqx"``.
    """

    def __init__(self, app_name: str = "intelliqx") -> None:
        self.app_name = app_name
        self.__modal_app: Any = None
        # agent_name -> modal.Function handle
        self.__functions: dict[str, Any] = {}
        self.__available = self._try_init()

    def _try_init(self) -> bool:
        try:
            import modal  # type: ignore

            self.__modal_app = modal.App(self.app_name)
            return True
        except (ImportError, OSError):
            return False

    async def invoke(self, request: InvocationRequest) -> InvocationResponse:
        """Invoke the named agent via Modal ``Function.remote()``.

        Offloads the blocking ``.remote()`` call to a worker thread.

        Args:
            request: The invocation descriptor.

        Returns:
            InvocationResponse with status ``"ok"``, ``"error"``,
            or ``"not_found"``.
        """
        if not self.__available or request.agent_name not in self.__functions:
            return InvocationResponse(
                agent_name=request.agent_name,
                output={},
                duration_ms=0,
                status="not_found",
                error=f"No modal function registered for {request.agent_name}",
            )
        fn = self.__functions[request.agent_name]
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
        if not self.__available:
            return
        import modal

        # ``Function.from_name`` resolves a deployed function by
        # (app, function-name). ``create_if_missing`` is a
        # no-op for functions that already exist.
        fn = modal.Function.from_name(self.app_name, agent_name, create_if_missing=True)
        self.__functions[agent_name] = fn
