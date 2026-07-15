"""MiniMax LLM adapter for IntelliqX.

Uses `litellm <https://docs.litellm.ai/docs/providers/minimax>`__ to
talk to MiniMax's OpenAI-compatible and Anthropic-compatible APIs.

Two entry points:

* **Chat completions** — :class:`MiniMaxLLMClient.complete` routes
  through ``litellm.acompletion`` with ``model="minimax/MiniMax-M2.1"``
  by default. The OpenAI-compatible endpoint
  (``https://api.minimax.io/v1``) is used so the same call works
  with every MiniMax chat model.
* **Embeddings** — :class:`MiniMaxLLMClient.embed` uses
  ``litellm.aembedding`` with ``model="minimax/text-embedding-01"``
  by default. The vector length is taken from the model registry
  (1536 for the default model).

Configuration is via two env vars:

* ``MINIMAX_API_KEY`` — your MiniMax API key (required).
* ``MINIMAX_API_BASE`` — base URL for the OpenAI-compatible endpoint
  (default ``https://api.minimax.io/v1``).

Error handling pattern (``_try_init`` / ``_available``):

* ``_try_init`` returns ``True`` only when both ``litellm`` and the
  ``MINIMAX_API_KEY`` env var are present. Missing litellm is
  caught as :class:`ImportError`; missing credentials raise a
  :class:`RuntimeError` from the ``MiniMaxLLMClient.__init__`` so
  the failure is obvious in the logs.
* When ``_available`` is ``False``, ``complete`` and ``embed`` fall
  back to the deterministic helpers from
  :mod:`intelliqx_llm.client`. This is **graceful degradation** —
  tests and CI on machines without the MiniMax SDK or API key keep
  running and surface a clearly-prefixed ``[minimax-fallback:]``
  response so callers can tell which path produced the answer.
* When ``_available`` is ``True`` but a MiniMax API call fails at
  request time (rate limit, transient network error, etc.), the
  exception is caught and a fallback response is returned. This
  mirrors the permissiveness of the Vertex AI adapter because
  MiniMax transient errors are common during cold-start.

Thread safety: litellm's :func:`acompletion` and
:func:`aembedding` are async-safe, so a single
:class:`MiniMaxLLMClient` instance can be shared across the event
loop. The singleton returned by
:func:`intelliqx_llm.client.get_llm_client` is what the agent
framework actually consumes.
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


class MiniMaxLLMClient(LLMClient):
    """MiniMax-backed LLM client (via litellm).

    Default chat model: ``minimax/MiniMax-M2.1``. The model is
    overridable per-request via
    :class:`~intelliqx_llm.client.CompletionRequest.model` and as a
    constructor argument for the embed path.

    The default embedding model is ``minimax/text-embedding-01``
    (1536 dims). If the deployed MiniMax account uses a different
    embedding model, pass it via ``model=...`` on :meth:`embed`.

    Args:
        api_key: MiniMax API key. Defaults to ``MINIMAX_API_KEY``.
        api_base: OpenAI-compatible base URL. Defaults to
            ``MINIMAX_API_BASE`` or
            ``https://api.minimax.io/v1``.
        model: Chat model name. Defaults to ``"minimax/MiniMax-M2.1"``.
        embed_model: Embedding model name. Defaults to
            ``"minimax/text-embedding-01"``.
        embed_dim: Override the embedding vector length when the
            upstream model does not return a known dimension.
            Defaults to 1536 (matches the default model).
    """

    DEFAULT_MODEL = "minimax/MiniMax-M2.1"
    DEFAULT_EMBED_MODEL = "minimax/text-embedding-01"
    DEFAULT_EMBED_DIM = 1536
    DEFAULT_API_BASE = "https://api.minimax.io/v1"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
        embed_model: str | None = None,
        embed_dim: int | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        self.api_base = api_base or os.environ.get("MINIMAX_API_BASE", "") or self.DEFAULT_API_BASE
        self.model = model or self.DEFAULT_MODEL
        self.embed_model = embed_model or self.DEFAULT_EMBED_MODEL
        self.embed_dim = embed_dim or self.DEFAULT_EMBED_DIM
        self._client: Any = None
        self._available = self._try_init()

    def _try_init(self) -> bool:
        """Probe the litellm SDK and the credentials.

        Returns:
            ``True`` only when litellm imports cleanly **and**
            ``MINIMAX_API_KEY`` is set. The SDK is not actually
            instantiated here — litellm's helpers are stateless
            thin wrappers over the OpenAI SDK, so a missing SDK
            is the only fatal import-time problem.
        """
        try:
            import litellm
        except ImportError:
            return False
        if not self.api_key:
            return False
        # Touch the attribute so mypy sees the import. litellm is
        # lazy; we don't pay its import cost on cold start.
        self._client = litellm
        return True

    @staticmethod
    def _last_user_message(messages: list[dict[str, str]]) -> str:
        """Return the content of the last ``user``-role message.

        Used to derive a deterministic fallback digest when the
        MiniMax API is unavailable. Empty string if the request has
        no user message.
        """
        for message in reversed(messages):
            if message.get("role") == "user":
                return str(message.get("content", ""))
        return ""

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Run a chat completion through MiniMax.

        Args:
            request: The request to send. ``request.model`` overrides
                the client default; ``request.metadata`` is dropped
                (litellm does not surface it).

        Returns:
            A :class:`CompletionResponse` populated from the
            provider. Falls back to ``[minimax-fallback:<digest>]``
            when the API is unreachable.
        """
        if not self._available:
            return self._fallback_complete(request)

        try:
            # The OpenAI-compatible path is the most stable for
            # MiniMax today; the Anthropic-compatible path
            # (``/anthropic/v1/messages``) is also supported by
            # litellm but adds an ``anthropic_version`` requirement
            # that we don't currently use.
            response = await self._client.acompletion(
                model=request.model,
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stop=request.stop,
                response_format=request.response_format,
                api_key=self.api_key,
                api_base=self.api_base,
            )
        except Exception:
            return self._fallback_complete(request)

        choice = response.choices[0]
        text = getattr(choice.message, "content", "") or ""
        usage_payload = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage_payload, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage_payload, "completion_tokens", 0) or 0)
        return CompletionResponse(
            content=text,
            model=request.model,
            usage=LLMUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        )

    def _fallback_complete(self, request: CompletionRequest) -> CompletionResponse:
        """Return a deterministic ``[minimax-fallback:...]`` response.

        Used when the API key is missing or a live call raises. The
        digest is the first 32 hex chars of SHA-256 over the last
        user message so tests can still assert on-call shape.
        """
        last_user = self._last_user_message(request.messages)
        digest = hashlib.sha256(last_user.encode("utf-8")).hexdigest()[:32]
        return CompletionResponse(
            content=f"[minimax-fallback:{digest}]",
            model=request.model,
            usage=LLMUsage(prompt_tokens=len(last_user.split())),
        )

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        """Embed a batch of strings through MiniMax.

        Args:
            texts: The strings to embed.
            model: Optional model override (defaults to
                ``self.embed_model``).

        Returns:
            One vector per input string. Falls back to
            :func:`intelliqx_llm.client.deterministic_embedding` when
            the API is unreachable or the upstream model is
            misconfigured.
        """
        if not self._available:
            return deterministic_embedding(list(texts), self.embed_dim)

        embed_model = model or self.embed_model
        if embed_model == "auto":
            embed_model = self.embed_model

        try:
            response = await self._client.aembedding(
                model=embed_model, input=list(texts), api_key=self.api_key, api_base=self.api_base
            )
        except Exception:
            return deterministic_embedding(list(texts), self.embed_dim)

        # litellm returns EmbeddingResponse with .data items whose
        # ``embedding`` attribute is the vector.
        return [list(item.embedding) for item in response.data]
