"""AWS Bedrock LLM adapter for AQIP.

Lazy-imports ``boto3``. If the SDK is missing or credentials are
unavailable, every method falls back to a deterministic mock so
local dev and CI on non-AWS machines still work. The fallback
content is prefixed with ``[bedrock-fallback:]`` so callers can tell
which path produced the response.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Sequence

from aqip_llm.client import (
    CompletionRequest,
    CompletionResponse,
    LLMClient,
    LLMUsage,
)


class BedrockLLMClient(LLMClient):
    """AWS Bedrock-backed LLM client.

    Default model: ``anthropic.claude-3-5-sonnet-20240620-v1:0``. The
    model is overridable per-request via
    :class:`~aqip_llm.client.CompletionRequest.model`.

    The request body is the Anthropic messages format. Bedrock
    requires ``anthropic_version`` and accepts a top-level
    ``system`` string extracted from the messages list.
    """

    DEFAULT_MODEL = "anthropic.claude-3-5-sonnet-20240620-v1:0"

    def __init__(self, region: str | None = None, model: str | None = None) -> None:
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.model = model or self.DEFAULT_MODEL
        self._client = None
        self._available = self._try_init()

    def _try_init(self) -> bool:
        try:
            import boto3  # type: ignore

            self._client = boto3.client("bedrock-runtime", region_name=self.region)
            return True
        except Exception:
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
            self._client.invoke_model,
            modelId=request.model,
            body=str(body).replace("'", '"'),
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
        # Bedrock doesn't expose a single embedding API; production
        # callers should use the dedicated embedding adapter
        # (Titan via boto3). We return 1024-dim deterministic
        # vectors in the fallback path so RAG tests still work.
        if not self._available:
            out = []
            for t in texts:
                digest = hashlib.sha256(t.encode("utf-8")).digest()
                vals: list[float] = []
                while len(vals) < 1024:
                    for b in digest:
                        vals.append((b / 255.0) * 2 - 1)
                        if len(vals) >= 1024:
                            break
                out.append(vals[:1024])
            return out
        # Real Bedrock Titan embed call would go here.
        raise NotImplementedError("Real Bedrock embeddings not implemented in this scaffold")
