"""GCP Vertex AI LLM adapter for AQIP.

Lazy-imports ``vertexai``. Falls back to a deterministic mock with
``[vertex-fallback:]`` prefix when the SDK or credentials are
unavailable.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence

from aqip_llm.client import CompletionRequest, CompletionResponse, LLMClient, LLMUsage


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
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "aqip-local")
        self.region = region or os.environ.get("AQIP_GCP_REGION", "us-central1")
        self.model = model or self.DEFAULT_MODEL
        self._client = None
        self._available = self._try_init()

    def _try_init(self) -> bool:
        try:
            from vertexai.generative_models import GenerativeModel  # type: ignore

            self._client = GenerativeModel(self.model)
            return True
        except Exception:
            return False

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self._available:
            last_user = next(
                (m["content"] for m in reversed(request.messages) if m.get("role") == "user"), ""
            )
            digest = hashlib.sha256(last_user.encode("utf-8")).hexdigest()[:32]
            return CompletionResponse(
                content=f"[vertex-fallback:{digest}]",
                model=request.model,
                usage=LLMUsage(prompt_tokens=len(last_user.split())),
            )
        # Real Vertex call would build a GenerativeModel and call
        # ``generate_content_async``. Not implemented in this scaffold;
        # production deployments must set up ADC / workload identity.
        raise NotImplementedError("Real Vertex AI calls not implemented in this scaffold")

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
        raise NotImplementedError("Vertex embeddings not implemented in this scaffold")
