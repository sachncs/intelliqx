"""AWS Bedrock LLM adapter for IntelliqX.

Lazy-imports ``boto3``. If the SDK is missing or credentials are
unavailable, every method falls back to a deterministic mock so
local dev and CI on non-AWS machines still work. The fallback
content is prefixed with ``[bedrock-fallback:]`` so callers can tell
which path produced the response.

Error handling pattern (``_try_init`` / ``_available``):

* ``_try_init`` catches ``(ImportError, OSError)``. ``ImportError``
  covers the absence of ``boto3``. ``OSError`` covers credential
  resolution failures at client-creation time (missing AWS
  credentials, invalid region, or STS errors).
* When ``_try_init`` returns ``False``, ``complete`` returns a
  deterministic mock response (SHA-256 of the last user message)
  prefixed with ``[bedrock-fallback:]``. ``embed`` returns a
  deterministic pseudo-embedding via ``deterministic_embedding``.
  This is **graceful degradation** — LLM-dependent tests and CI
  keep running on non-AWS machines.
* When ``_try_init`` returns ``True`` but Bedrock invocation fails
  at call time (e.g. model access denied, throttling), the
  ``embed`` method falls back to ``deterministic_embedding``. The
  ``complete`` method lets the boto3 exception propagate so the
  caller can decide whether to retry or fail.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Sequence
from typing import Any

from intelliqx_llm.client import (
    CompletionRequest,
    CompletionResponse,
    LLMClient,
    LLMUsage,
    deterministic_embedding,
)


class BedrockLLMClient(LLMClient):
    """AWS Bedrock-backed LLM client.

    Default model: ``anthropic.claude-3-5-sonnet-20240620-v1:0``. The
    model is overridable per-request via
    :class:`~intelliqx_llm.client.CompletionRequest.model`.

    The request body is the Anthropic messages format. Bedrock
    requires ``anthropic_version`` and accepts a top-level
    ``system`` string extracted from the messages list.
    """

    DEFAULT_MODEL = "anthropic.claude-3-5-sonnet-20240620-v1:0"

    def __init__(self, region: str | None = None, model: str | None = None) -> None:
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.model = model or self.DEFAULT_MODEL
        self._client: Any = None
        self._available = self._try_init()

    def _try_init(self) -> bool:
        try:
            import boto3  # type: ignore

            self._client = boto3.client("bedrock-runtime", region_name=self.region)
            return True
        except (ImportError, OSError):
            return False

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self._available:
            # Deterministic fallback for tests/dev.
            last_user = next(
                (m["content"] for m in reversed(request.messages) if m.get("role") == "user"), ""
            )
            digest = hashlib.sha256(last_user.encode("utf-8")).hexdigest()[:32]
            return CompletionResponse(
                content=f"[bedrock-fallback:{digest}]",
                model=request.model,
                usage=LLMUsage(prompt_tokens=len(last_user.split())),
            )
        # Build the Anthropic-style body. Bedrock expects
        # ``anthropic_version``, ``max_tokens``, ``temperature``,
        # ``messages``, and optionally ``system``.
        system = next((m["content"] for m in request.messages if m.get("role") == "system"), "")
        messages = [m for m in request.messages if m.get("role") != "system"]
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if system:
            body["system"] = system
        # Offload the boto3 call to a worker thread.
        response = await asyncio.to_thread(
            self._client.invoke_model, modelId=request.model, body=str(body).replace("'", '"')
        )
        import json as _json

        payload = _json.loads(response["body"].read())
        text = payload.get("content", [{}])[0].get("text", "")
        usage_dict = payload.get("usage", {})
        return CompletionResponse(
            content=text,
            model=request.model,
            usage=LLMUsage(
                prompt_tokens=usage_dict.get("input_tokens", 0),
                completion_tokens=usage_dict.get("output_tokens", 0),
            ),
        )

    async def embed(self, texts: Sequence[str], *, model: str = "auto") -> list[list[float]]:
        if not self._available:
            return deterministic_embedding(texts, 1024)
        try:
            import json as _json

            TITAN_EMBED_MODEL = "amazon.titan-embed-text-v1:0"
            out: list[list[float]] = []
            for t in texts:
                body = _json.dumps({"inputText": t})
                response = await asyncio.to_thread(
                    self._client.invoke_model, modelId=TITAN_EMBED_MODEL, body=body
                )
                payload = _json.loads(response["body"].read())
                out.append(payload["embedding"])
            return out
        except Exception:
            return deterministic_embedding(texts, 1024)
