"""GCP Cloud Functions / Cloud Run compute adapter for IntelliqX.

Each agent is deployed as a function URL named
``intelliqx-{agent_name}`` and exposed as an HTTP-triggered function.
The adapter POSTs the request payload as JSON and parses the
response the same way.

Error handling pattern (``_try_init`` / ``_available``):

* ``_try_init`` catches ``ImportError`` only (not ``OSError``)
  because ``httpx`` is a pure-Python HTTP client that does not
  perform network I/O or credential resolution at import time.
  The URL is constructed at call time, not at init time.
* When ``_try_init`` returns ``False``, ``invoke`` returns an
  ``InvocationResponse`` with ``status="not_found"`` and the message
  ``"httpx SDK is not installed"``. This is **graceful degradation**
  — the orchestrator keeps running.
* When ``_try_init`` returns ``True`` but the function URL is
  misconfigured or unreachable, the HTTP error or exception is
  caught and returned as an ``InvocationResponse`` with
  ``status="error"``. This keeps the orchestration loop alive.
"""

from __future__ import annotations

import os
import time

from intelliqx_compute.runtime import ComputeRuntime, InvocationRequest, InvocationResponse


class GCPFunctionsComputeRuntime(ComputeRuntime):
    """Invokes agents via GCP Cloud Functions (HTTP trigger) or Cloud Run.

    Args:
        project_id: GCP project id. Defaults to ``GOOGLE_CLOUD_PROJECT``
            env var, then ``"intelliqx-local"``.
        region: GCP region. Defaults to ``INTELLIQX_GCP_REGION``, then
            ``us-central-1``.
    """

    def __init__(self, project_id: str | None = None, region: str | None = None) -> None:
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "intelliqx-local")
        self.region = region or os.environ.get("INTELLIQX_GCP_REGION", "us-central1")
        self._available = self._try_init()

    def _try_init(self) -> bool:
        """Check whether the ``httpx`` SDK is importable."""
        try:
            import httpx  # noqa: F401

            return True
        except ImportError:
            return False

    async def invoke(self, request: InvocationRequest) -> InvocationResponse:
        """Invoke the named agent via GCP Cloud Functions HTTP POST.

        Constructs the URL from the configured region and project id
        and POSTs the request body as JSON. Returns a structured
        response for all outcomes; errors are captured rather than
        raised.

        Args:
            request: The invocation descriptor.

        Returns:
            InvocationResponse with status ``"ok"``, ``"error"``,
            or ``"not_found"``.
        """
        if not self._available:
            return InvocationResponse(
                agent_name=request.agent_name,
                output={},
                duration_ms=0,
                status="not_found",
                error="httpx SDK is not installed",
            )
        import httpx

        url = f"https://{self.region}-{self.project_id}.cloudfunctions.net/intelliqx-{request.agent_name}"
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
                r = await client.post(url, json=request.model_dump(mode="json"))
            duration_ms = int((time.monotonic() - start) * 1000)
            if r.status_code != 200:
                return InvocationResponse(
                    agent_name=request.agent_name,
                    output={},
                    duration_ms=duration_ms,
                    status="error",
                    error=f"HTTP {r.status_code}: {r.text[:200]}",
                )
            data = r.json()
            return InvocationResponse(
                agent_name=request.agent_name,
                output=data.get("output", {}),
                duration_ms=duration_ms,
                status=data.get("status", "ok"),
                error=data.get("error"),
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
        """No-op: Cloud Function registration happens at deploy time.

        Agent URLs are provisioned via the GCP Terraform module; this
        method exists only to satisfy the abstract interface.
        """
        pass
