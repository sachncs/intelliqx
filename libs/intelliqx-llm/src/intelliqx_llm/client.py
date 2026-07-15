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
from abc import ABC, abstractmethod
from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "LLM_BACKEND_REGISTRY",
    "CompletionRequest",
    "CompletionResponse",
    "FakeLLMClient",
    "LLMClient",
    "LLMUsage",
    "deterministic_embedding",
    "get_llm_client",
    "list_llm_backends",
    "register_llm_backend",
    "reset_llm_client",
    "set_llm_client",
]


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


class LLMClient(ABC):
    """Abstract LLM client.

    Subclasses implement :meth:`complete` and :meth:`embed`. The
    platform consumes the abstract type so agent code is portable
    across cloud providers. Declared as a real :class:`ABC` so the
    runtime blocks attempts to instantiate it directly and to
    document the contract for IDE auto-complete.
    """

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Run a chat completion.

        Args:
            request: The request to send.

        Returns:
            The provider's response.
        """

    @abstractmethod
    async def embed(
        self, texts: Sequence[str], *, model: str = "auto"
    ) -> list[list[float]]:
        """Embed a batch of strings.

        Args:
            texts: The strings to embed.
            model: Optional model override.

        Returns:
            One vector per input string, each of length
            ``self.dim`` (or the model's declared dim).
        """


@lru_cache(maxsize=2048)
def _hash_embedding(text: str, dim: int) -> tuple[float, ...]:
    """Cached SHA-256-derived embedding for ``text`` at ``dim`` length.

    ``lru_cache`` is safe here because the function is a pure
    function of its arguments. The whole-vector tuple is the cache
    value so callers can index it without list construction.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vals: list[float] = []
    while len(vals) < dim:
        for b in digest:
            vals.append((b / 255.0) * 2 - 1)
            if len(vals) >= dim:
                break
    return tuple(vals[:dim])


def deterministic_embedding(texts: Sequence[str], dim: int) -> list[list[float]]:
    """Build deterministic hash-based embeddings for fallback / test paths.

    Each output vector is derived from the SHA-256 of the input text,
    repeated and scaled to ``[-1, 1]`` until it reaches ``dim`` entries.
    The result is **not** semantically meaningful but is deterministic
    and bounded, which is sufficient for RAG pipeline tests. Per-text
    embeddings are cached so a batch of duplicates only hashes once.
    """
    return [list(_hash_embedding(t, dim)) for t in texts]


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


SINGLETON: LLMClient | None = None


LLM_BACKEND_REGISTRY: dict[str, type[LLMClient]] = {
    "fake": FakeLLMClient,
}


def register_llm_backend(name: str, factory: type[LLMClient]) -> None:
    """Register a backend under ``name``.

    The factory class is captured at registration time and used by
    :func:`get_llm_client` whenever ``INTELLIQX_LLM_BACKEND=name``.
    Registering an existing name replaces the previous factory, which
    is the intended escape hatch for tests.

    Backend name lookup is exact-match; the convention is lowercase
    short codes (``"fake"``, ``"bedrock"``, ``"vertex"``, ``"vllm"``,
    ``"minimax"``).
    """
    LLM_BACKEND_REGISTRY[name] = factory


def _load_default_backends() -> None:
    """Populate the registry with built-in backend classes.

    Lazy + best-effort: classes whose SDK is missing get skipped so
    the platform still boots. The ``fake`` backend is registered at
    module-import time above; the cloud backends are imported here.
    """
    if "bedrock" in LLM_BACKEND_REGISTRY:
        return
    try:
        from intelliqx_llm.aws import BedrockLLMClient

        LLM_BACKEND_REGISTRY["bedrock"] = BedrockLLMClient
    except ImportError:
        pass
    try:
        from intelliqx_llm.gcp import VertexLLMClient

        LLM_BACKEND_REGISTRY["vertex"] = VertexLLMClient
    except ImportError:
        pass
    try:
        from intelliqx_llm.modal import VLLMModalLLMClient

        LLM_BACKEND_REGISTRY["vllm"] = VLLMModalLLMClient
    except ImportError:
        pass
    try:
        from intelliqx_llm.minimax import MiniMaxLLMClient

        LLM_BACKEND_REGISTRY["minimax"] = MiniMaxLLMClient
    except ImportError:
        pass


def list_llm_backends() -> tuple[str, ...]:
    """Return the names of every registered backend (sorted)."""
    return tuple(sorted(LLM_BACKEND_REGISTRY))


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
    global SINGLETON
    if SINGLETON is None:
        backend = os.environ.get("INTELLIQX_LLM_BACKEND", "fake")
        _load_default_backends()
        factory = LLM_BACKEND_REGISTRY.get(backend)
        if factory is None:
            available = ", ".join(list_llm_backends())
            raise RuntimeError(
                f"LLM backend {backend!r} not registered. "
                f"Available backends: {available}. "
                "Use INTELLIQX_LLM_BACKEND=fake for tests/dev."
            )
        SINGLETON = factory()
    return SINGLETON


def set_llm_client(client: LLMClient) -> None:
    """Replace the singleton LLM client.

    Used by application bootstrap to install a configured cloud
    adapter (Bedrock, Vertex, vLLM, or MiniMax) before the first
    :func:`get_llm_client` call.
    """
    global SINGLETON
    SINGLETON = client


def reset_llm_client() -> None:
    """Clear the singleton LLM client (for tests)."""
    global SINGLETON
    SINGLETON = None
