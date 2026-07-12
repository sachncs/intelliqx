"""GCP Cloud Functions / Cloud Run compute adapter for IntelliqX.

Each agent is deployed as a function URL named
``intelliqx-{agent_name}`` and exposed as an HTTP-triggered function.
The adapter POSTs the request payload as JSON and parses the
response the same way.
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
        self._available = False

    async def invoke(self, request: InvocationRequest) -> InvocationResponse:
        try:
            import httpx  # type: ignore
        except ImportError as e:
            return InvocationResponse(
                agent_name=request.agent_name,
                output={},
                duration_ms=0,
                status="not_found",
                error=str(e),
            )
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
        # Function registration happens at deploy time, not runtime.
        pass
