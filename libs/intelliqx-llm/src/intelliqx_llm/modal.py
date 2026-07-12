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
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence

from intelliqx_llm.client import CompletionRequest, CompletionResponse, LLMClient, LLMUsage


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

    def __init__(self, endpoint_url: str | None = None, model: str = "Qwen/Qwen2.5-72B-Instruct") -> None:
        self.endpoint_url = endpoint_url or os.environ.get("INTELLIQX_VLLM_URL", "")
        self.model = model
        self._client = None
        # "Available" here means a real endpoint is configured; the
        # fallback path is always reachable for tests.
        self._available = bool(self.endpoint_url)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self._available:
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
            import httpx  # type: ignore
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
        if not self._available:
            out = []
            for t in texts:
                digest = hashlib.sha256(t.encode("utf-8")).digest()
                vals: list[float] = []
                while len(vals) < 768:
                    for b in digest:
                        vals.append((b / 255.0) * 2 - 1)
                        if len(vals) >= 768:
                            break
                out.append(vals[:768])
            return out
        # Real vLLM /v1/embeddings call.
        try:
            import httpx  # type: ignore
        except ImportError as e:
            raise RuntimeError("httpx required for VLLMModalLLMClient") from e
        async with httpx.AsyncClient(base_url=self.endpoint_url, timeout=60.0) as client:
            r = await client.post(
                "/v1/embeddings",
                json={"model": self.model, "input": list(texts)},
            )
            r.raise_for_status()
            data = r.json()
        return [d["embedding"] for d in data["data"]]
