"""AWS Lambda / Fargate compute adapter for IntelliqX.

Invokes agents via AWS Lambda. The convention is one Lambda function
per agent, named ``intelliqx-{agent_name}`` (e.g. ``intelliqx-planner``,
``intelliqx-execution``). For long-running agents whose single execution
can exceed the 15-minute Lambda limit, use AWS Fargate instead (a
separate adapter in production deployments).

Error handling pattern (``_try_init`` / ``_available``):

* ``_try_init`` catches ``(ImportError, OSError)``. ``ImportError``
  covers the absence of ``boto3``. ``OSError`` covers credential
  resolution failures at client-creation time (missing AWS
  credentials, invalid region, or network error resolving the
  Lambda endpoint).
* When ``_try_init`` returns ``False``, ``invoke`` returns an
  ``InvocationResponse`` with ``status="not_found"`` and a
  descriptive error message. This is **graceful degradation** — the
  compute layer degrades to a "not found" response rather than
  crashing the orchestrator.
* When ``_try_init`` returns ``True`` but Lambda invocation fails
  at call time, the exception is caught and returned as an
  ``InvocationResponse`` with ``status="error"``. This keeps the
  orchestration loop alive even when individual agent invocations
  fail transiently.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

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
        self.__client: Any = None
        self.__available = self._try_init()

    def _try_init(self) -> bool:
        try:
            import boto3  # type: ignore

            self.__client = boto3.client("lambda", region_name=self.region)
            return True
        except (ImportError, OSError):
            return False

    async def invoke(self, request: InvocationRequest) -> InvocationResponse:
        """Invoke the named agent via AWS Lambda ``RequestResponse``.

        Offloads the blocking ``lambda.invoke`` call to a worker
        thread. Returns a structured ``InvocationResponse`` for all
        outcomes; errors are captured rather than raised so the
        orchestrator can branch on ``status``.

        Args:
            request: The invocation descriptor.

        Returns:
            InvocationResponse with one of statuses
            ``"ok"``, ``"error"``, or ``"not_found"``.
        """
        if not self.__available:
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
                self.__client.invoke,
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
        """No-op: Lambda registration happens at deploy time.

        Agent functions are provisioned via the CDK stack
        (``intelliqx-{agent_name}``); this method exists only to
        satisfy the abstract interface.
        """
        pass
