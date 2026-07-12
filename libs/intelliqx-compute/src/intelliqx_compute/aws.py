"""AWS Lambda / Fargate compute adapter for AQIP.

Invokes agents via AWS Lambda. The convention is one Lambda function
per agent, named ``aqip-{agent_name}`` (e.g. ``aqip-planner``,
``aqip-execution``). For long-running agents whose single execution
can exceed the 15-minute Lambda limit, use AWS Fargate instead (a
separate adapter in production deployments).
"""

from __future__ import annotations

import json
import os
import time

from intelliqx_compute.runtime import (
    ComputeRuntime,
    InvocationRequest,
    InvocationResponse,
)


class AWSLambdaComputeRuntime(ComputeRuntime):
    """Invokes agents via AWS Lambda.

    Args:
        region: AWS region. Defaults to ``AWS_REGION`` env var, then
            ``us-east-1``.
    """

    def __init__(self, region: str | None = None) -> None:
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self._client = None
        self._available = self._try_init()

    def _try_init(self) -> bool:
        try:
            import boto3  # type: ignore

            self._client = boto3.client("lambda", region_name=self.region)
            return True
        except Exception:
            return False

    async def invoke(self, request: InvocationRequest) -> InvocationResponse:
        if not self._available:
            return InvocationResponse(
                agent_name=request.agent_name,
                output={},
                duration_ms=0,
                status="not_found",
                error="AWSLambdaComputeRuntime requires boto3 + AWS credentials",
            )
        import asyncio

        start = time.monotonic()
        try:
            # Synchronous RequestResponse invoke. The boto3 call is
            # blocking; we offload to a worker thread.
            response = await asyncio.to_thread(
                self._client.invoke,
                FunctionName=f"intelliqx-{request.agent_name}",
                InvocationType="RequestResponse",
                Payload=json.dumps(request.model_dump(mode="json")),
            )
            payload = json.loads(response["Payload"].read())
            duration_ms = int((time.monotonic() - start) * 1000)
            return InvocationResponse(
                agent_name=request.agent_name,
                output=payload.get("output", {}),
                duration_ms=duration_ms,
                status=payload.get("status", "ok"),
                error=payload.get("error"),
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
        # Lambda registration happens at deploy time, not runtime.
        pass
