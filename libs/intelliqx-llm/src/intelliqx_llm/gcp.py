"""GCP Vertex AI LLM adapter for IntelliqX.

Lazy-imports ``vertexai``. Falls back to a deterministic mock with
``[vertex-fallback:]`` prefix when the SDK or credentials are
unavailable.

Error handling pattern (``_try_init`` / ``_available``):

* ``_try_init`` catches ``(ImportError, OSError)``. ``ImportError``
  covers the absence of the ``google-cloud-aiplatform`` package
  (which provides ``vertexai``). ``OSError`` covers credential
  resolution failures (missing ``GOOGLE_APPLICATION_CREDENTIALS``,
  expired service-account key, or unreachable metadata server).
* When ``_try_init`` returns ``False``, ``complete`` returns a
  deterministic mock response (SHA-256 of the last user message)
  prefixed with ``[vertex-fallback:]``. ``embed`` returns a
  deterministic pseudo-embedding. This is **graceful degradation**
  — LLM-dependent tests and CI keep running on non-GCP machines.
* When ``_try_init`` returns ``True`` but Vertex AI invocation
  fails at call time (e.g. model not found, quota exceeded), the
  exception is caught and a ``[vertex-fallback:]`` response is
  returned. This is more permissive than the AWS adapter because
  Vertex AI transient errors are common during auto-scaling.
"""

from __future__ import annotations

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


class VertexLLMClient(LLMClient):
    """Vertex AI Gemini client.

    Default model: ``gemini-2.0-flash-exp``. Vertex AI is the GCP
    equivalent of AWS Bedrock; both are managed-model services with
    per-request billing.

    The 768-dim embedding fallback matches the size of Vertex's
    ``text-embedding-005`` model.
    """

    DEFAULT_MODEL = "gemini-2.0-flash-exp"

    def __init__(
        self,
        project_id: str | None = None,
        region: str | None = None,
        model: str | None = None,
    ) -> None:
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "intelliqx-local")
        self.region = region or os.environ.get("INTELLIQX_GCP_REGION", "us-central1")
        self.model = model or self.DEFAULT_MODEL
        self.__client: Any = None
        self.__available = self._try_init()

    def _try_init(self) -> bool:
        try:
            from vertexai.generative_models import GenerativeModel  # type: ignore

            self.__client = GenerativeModel(self.model)
            return True
        except (ImportError, OSError):
            return False

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self.__available:
            last_user = next(
                (m["content"] for m in reversed(request.messages) if m.get("role") == "user"), ""
            )
            digest = hashlib.sha256(last_user.encode("utf-8")).hexdigest()[:32]
            return CompletionResponse(
                content=f"[vertex-fallback:{digest}]",
                model=request.model,
                usage=LLMUsage(prompt_tokens=len(last_user.split())),
            )
        try:
            from vertexai.generative_models import GenerationConfig

            system_msg = next(
                (m["content"] for m in request.messages if m.get("role") == "system"), None
            )
            contents = [
                {"role": m["role"], "parts": [m["content"]]}
                for m in request.messages
                if m.get("role") != "system"
            ]
            gen_config = GenerationConfig(
                temperature=request.temperature,
                max_output_tokens=request.max_tokens,
            )
            gen_kwargs: dict[str, Any] = {"generation_config": gen_config}
            if system_msg:
                gen_kwargs["system_instruction"] = system_msg
            response = await self.__client.generate_content_async(
                contents=contents,
                **gen_kwargs,
            )
            text = response.text or ""
            usage = LLMUsage()
            if response.usage_metadata:
                usage = LLMUsage(
                    prompt_tokens=getattr(response.usage_metadata, "prompt_token_count", 0) or 0,
                    completion_tokens=getattr(response.usage_metadata, "candidates_token_count", 0)
                    or 0,
                )
            return CompletionResponse(
                content=text,
                model=request.model,
                usage=usage,
            )
        except Exception:
            last_user = next(
                (m["content"] for m in reversed(request.messages) if m.get("role") == "user"), ""
            )
            digest = hashlib.sha256(last_user.encode("utf-8")).hexdigest()[:32]
            return CompletionResponse(
                content=f"[vertex-fallback:{digest}]",
                model=request.model,
                usage=LLMUsage(prompt_tokens=len(last_user.split())),
            )

    async def embed(self, texts: Sequence[str], *, model: str = "auto") -> list[list[float]]:
        if not self.__available:
            return deterministic_embedding(texts, 768)
        try:
            import asyncio

            from vertexai.language_models import TextEmbeddingModel  # type: ignore

            embed_model = TextEmbeddingModel.from_pretrained("textembedding-gecko@003")
            result = await asyncio.to_thread(embed_model.get_embeddings, texts)
            return [e.values for e in result]
        except Exception:
            return deterministic_embedding(texts, 768)
