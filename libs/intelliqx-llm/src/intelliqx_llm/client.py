"""LLM client interface and deterministic fake implementation.

The :class:`LLMClient` interface is intentionally small. The two
operations every agent uses:

* ``complete(request)`` — a chat-style completion.
* ``embed(texts, *, model)`` — vectorise a batch of strings.

The :class:`FakeLLMClient` is the reference implementation used in
tests. It is **deterministic** (the same input always produces the
same output) so tests are reproducible. Two modes:

* **Registered markers.** If the last user message contains a
  substring registered via :meth:`register_response`, the
  registered string is returned verbatim.
* **Hash fallback.** Otherwise the response is a hash-derived
  placeholder prefixed with ``[fake:``. The hash is the first 32
  hex chars of SHA-256 over the input.

Token accounting is approximated by whitespace splitting; production
clients fill in real counts.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LLMUsage(BaseModel):
    """Token usage accounting.

    The fake client fills ``prompt_tokens`` and ``completion_tokens``
    by whitespace-splitting the input. Production clients receive
    authoritative counts from the LLM provider and fill
    ``cost_usd`` as well.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


class CompletionRequest(BaseModel):
    """LLM completion request.

    Matches the OpenAI chat-completions shape closely so the
    production adapters can serialise requests with minimal
    translation. ``metadata`` is IntelliqX-specific — it lets callers
    attach tenant ids, run ids, etc. without changing the model.
    """

    model_config = ConfigDict(extra="forbid")

    model: str = "auto"
    messages: list[dict[str, str]]
    temperature: float = 0.0
    max_tokens: int = 1024
    stop: list[str] | None = None
    response_format: dict[str, str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompletionResponse(BaseModel):
    """LLM completion response.

    Attributes:
        content: The assistant message.
        model: The model that produced the response (may differ
            from the request if the runtime auto-routes).
        finish_reason: ``"stop"``, ``"length"``, etc. Mirrors the
            OpenAI field.
        usage: Token usage accounting.
    """

    model_config = ConfigDict(extra="forbid")

    content: str
    model: str
    finish_reason: str = "stop"
    usage: LLMUsage = Field(default_factory=LLMUsage)


class LLMClient:
    """Abstract LLM client.

    Subclasses implement ``complete`` and ``embed``. The platform
    consumes the abstract type so agent code is portable across cloud
    providers.
    """

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Run a chat completion.

        Args:
            request: The request to send.

        Returns:
            The provider's response.
        """
        raise NotImplementedError

    async def embed(self, texts: Sequence[str], *, model: str = "auto") -> list[list[float]]:
        """Embed a batch of strings.

        Args:
            texts: The strings to embed.
            model: Optional model override.

        Returns:
            One vector per input string, each of length
            ``self.dim`` (or the model's declared dim).
        """
        raise NotImplementedError


def deterministic_embedding(texts: Sequence[str], dim: int) -> list[list[float]]:
    """Build deterministic hash-based embeddings for fallback / test paths.

    Each output vector is derived from the SHA-256 of the input text,
    repeated and scaled to ``[-1, 1]`` until it reaches ``dim`` entries.
    The result is **not** semantically meaningful but is deterministic
    and bounded, which is sufficient for RAG pipeline tests.
    """
    out: list[list[float]] = []
    for t in texts:
        digest = hashlib.sha256(t.encode("utf-8")).digest()
        vals: list[float] = []
        while len(vals) < dim:
            for b in digest:
                vals.append((b / 255.0) * 2 - 1)
                if len(vals) >= dim:
                    break
        out.append(vals[:dim])
    return out


class FakeLLMClient(LLMClient):
    """Deterministic fake LLM client for tests.

    Two response modes:
        1. If a marker substring is registered (see
           :meth:`register_response`) and the last user message
           contains it, the registered response is returned.
        2. Otherwise the response is a hash-derived placeholder
           starting with ``[fake:``.

    Embeddings are derived from the SHA-256 of each input string;
    they are deterministic and bounded but **not** semantically
    meaningful. They are good enough for tests that exercise the
    RAG / hybrid-retrieval pipeline without needing a real model.
    """

    def __init__(self, *, dim: int = 768, latency_ms: int = 1) -> None:
        self.responses: dict[str, str] = {}
        self.dim = dim
        self.latency_ms = latency_ms
        self.call_log: list[CompletionRequest] = []

    def register_response(self, marker: str, response: str) -> None:
        """Register a deterministic response for a marker substring.

        Args:
            marker: Substring to look for in the last user message.
            response: The literal response to return when the marker
                is found.
        """
        self.responses[marker] = response

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Produce a deterministic response.

        Sleeps for ``latency_ms`` milliseconds so tests can exercise
        ordering without needing real network I/O.
        """
        await asyncio.sleep(self.latency_ms / 1000.0)
        self.call_log.append(request)
        last_user = next(
            (m["content"] for m in reversed(request.messages) if m.get("role") == "user"), ""
        )
        # ``for ... else`` runs the ``else`` block only if the loop
        # completes without ``break`` — i.e. no marker matched.
        for marker, response in self.responses.items():
            if marker in last_user:
                content = response
                break
        else:
            digest = hashlib.sha256(last_user.encode("utf-8")).hexdigest()[:32]
            content = f"[fake:{digest}]"

        prompt_tokens = sum(len(m.get("content", "").split()) for m in request.messages)
        completion_tokens = len(content.split())
        return CompletionResponse(
            content=content,
            model=request.model,
            usage=LLMUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        )

    async def embed(self, texts: Sequence[str], *, model: str = "auto") -> list[list[float]]:
        """Embed ``texts`` deterministically.

        Each output vector is derived from the SHA-256 of each input,
        repeated and scaled to ``[-1, 1]`` until it reaches ``self.dim``
        entries.  The result is bounded but **not** semantically meaningful.
        """
        await asyncio.sleep(self.latency_ms / 1000.0)
        return deterministic_embedding(texts, self.dim)


_SINGLETON: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return the configured LLM client.

    Resolution:
        * ``INTELLIQX_LLM_BACKEND=fake`` (default) → :class:`FakeLLMClient`.
        * ``bedrock`` → :class:`intelliqx_llm.aws.BedrockLLMClient`.
        * ``vertex`` → :class:`intelliqx_llm.gcp.VertexLLMClient`.
        * ``vllm`` → :class:`intelliqx_llm.modal.VLLMModalLLMClient`.
        * ``minimax`` → :class:`intelliqx_llm.minimax.MiniMaxLLMClient`.
        * Anything else raises a clear :class:`RuntimeError`.

    Each cloud adapter implements the same graceful-degradation
    pattern: if the SDK is missing or credentials are unavailable,
    the adapter returns a deterministic fallback so the rest of
    the platform keeps working.
    """
    global _SINGLETON
    if _SINGLETON is None:
        backend = os.environ.get("INTELLIQX_LLM_BACKEND", "fake")
        if backend == "fake":
            _SINGLETON = FakeLLMClient()
        elif backend == "bedrock":
            from intelliqx_llm.aws import BedrockLLMClient

            _SINGLETON = BedrockLLMClient()
        elif backend == "vertex":
            from intelliqx_llm.gcp import VertexLLMClient

            _SINGLETON = VertexLLMClient()
        elif backend == "vllm":
            from intelliqx_llm.modal import VLLMModalLLMClient

            _SINGLETON = VLLMModalLLMClient()
        elif backend == "minimax":
            from intelliqx_llm.minimax import MiniMaxLLMClient

            _SINGLETON = MiniMaxLLMClient()
        else:
            raise RuntimeError(
                f"LLM backend {backend!r} not available in this runtime. "
                "Use INTELLIQX_LLM_BACKEND=fake for tests/dev."
            )
    return _SINGLETON


def set_llm_client(client: LLMClient) -> None:
    """Replace the singleton LLM client.

    Used by application bootstrap to install a configured cloud
    adapter (Bedrock, Vertex, vLLM, or MiniMax) before the first
    :func:`get_llm_client` call.
    """
    global _SINGLETON
    _SINGLETON = client


def reset_llm_client() -> None:
    """Clear the singleton LLM client (for tests)."""
    global _SINGLETON
    _SINGLETON = None
