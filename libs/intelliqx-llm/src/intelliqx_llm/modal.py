"""Modal LLM adapter.

Two strategies:

* **vLLM self-hosted** on Modal GPU — used for cost-sensitive or
  privacy-sensitive deployments. The default model is
  ``Qwen/Qwen2.5-72B-Instruct``; the adapter talks OpenAI-compatible
  HTTP to the vLLM endpoint exposed by a ``modal.web_endpoint``.
* **LiteLLM-routed hosted models** — when ``endpoint_url`` is empty
  the adapter falls back to a deterministic mock prefixed with
  ``[vllm-fallback:]``.

The OpenAI-compatible wire format (``/v1/chat/completions`` and
``/v1/embeddings``) means the same code works against any vLLM
deployment regardless of the underlying model.

Error handling pattern (``_available`` flag):

* Unlike other adapters, ``_available`` is set from
  ``bool(self.endpoint_url)`` — a simple env-var check rather than
  an import test — because the real dependency (``httpx``) is only
  imported inside ``complete``/``embed`` when ``_available`` is
  ``True``. If ``httpx`` is missing at that point, a loud
  ``RuntimeError`` is raised.
* When ``_available`` is ``False`` (no ``endpoint_url`` configured),
  ``complete`` returns a deterministic mock response prefixed with
  ``[vllm-fallback:]`` and ``embed`` returns a deterministic
  pseudo-embedding. This is **graceful degradation** — Modal-less
  CI and local dev keep working.
* When ``_available`` is ``True`` but the vLLM endpoint is
  unreachable or returns an error, the ``httpx`` exception
  propagates (via ``r.raise_for_status()``). This is **fail loud**
  — silent fallback would mask a real deployment problem.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence

from intelliqx_llm.client import (
    CompletionRequest,
    CompletionResponse,
    LLMClient,
    LLMUsage,
    deterministic_embedding,
)


class VLLMModalLLMClient(LLMClient):
    """vLLM hosted on Modal (GPU-backed).

    The agent invokes the LLM via HTTP to the vLLM endpoint exposed
    by a ``modal.web_endpoint``. In tests and dev (when
    ``endpoint_url`` is empty) the adapter falls back to a
    deterministic mock.

    Args:
        endpoint_url: The base URL of the vLLM server. Defaults to
            the ``INTELLIQX_VLLM_URL`` env var.
        model: The model name to send in requests.
    """

    def __init__(
        self, endpoint_url: str | None = None, model: str = "Qwen/Qwen2.5-72B-Instruct"
    ) -> None:
        self.endpoint_url = endpoint_url or os.environ.get("INTELLIQX_VLLM_URL", "")
        self.model = model
        self.__client = None
        # "Available" here means a real endpoint is configured; the
        # fallback path is always reachable for tests.
        self.__available = bool(self.endpoint_url)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self.__available:
            last_user = next(
                (m["content"] for m in reversed(request.messages) if m.get("role") == "user"), ""
            )
            digest = hashlib.sha256(last_user.encode("utf-8")).hexdigest()[:32]
            return CompletionResponse(
                content=f"[vllm-fallback:{digest}]",
                model=request.model,
                usage=LLMUsage(prompt_tokens=len(last_user.split())),
            )
        # Real vLLM HTTP call (OpenAI-compatible /v1/chat/completions).
        try:
            import httpx
        except ImportError as e:
            raise RuntimeError("httpx required for VLLMModalLLMClient") from e
        async with httpx.AsyncClient(base_url=self.endpoint_url, timeout=60.0) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": request.messages,
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                },
            )
            r.raise_for_status()
            data = r.json()
        choice = data["choices"][0]
        return CompletionResponse(
            content=choice["message"]["content"],
            model=self.model,
            usage=LLMUsage(
                prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
            ),
        )

    async def embed(self, texts: Sequence[str], *, model: str = "auto") -> list[list[float]]:
        if not self.__available:
            return deterministic_embedding(texts, 768)
        # Real vLLM /v1/embeddings call.
        try:
            import httpx
        except ImportError as e:
            raise RuntimeError("httpx required for VLLMModalLLMClient") from e
        async with httpx.AsyncClient(base_url=self.endpoint_url, timeout=60.0) as client:
            r = await client.post(
                "/v1/embeddings", json={"model": self.model, "input": list(texts)}
            )
            r.raise_for_status()
            data = r.json()
        return [d["embedding"] for d in data["data"]]
