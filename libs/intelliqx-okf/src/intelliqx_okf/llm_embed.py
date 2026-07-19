"""LLM-backed :class:`Embedder` adapter.

Production embedder. The default test embedder is
:data:`FakeEmbedder`. Call :func:`LLMEmbedder.from_default` or pass an
explicit :class:`Embedder` when constructing the
:class:`~intelliqx_okf.index.Index`.

The adapter forwards to the existing LLM client and converts the
async ``client.embed`` call into the single-string
:func:`Embedder.embed` API used by :class:`~intelliqx_okf.index.Index`.
"""

from __future__ import annotations

import asyncio

from intelliqx_llm.client import LLMClient, get_llm_client

from intelliqx_okf.embed import Embedder


class LLMEmbedder(Embedder):
    """Adapt an :class:`LLMClient` to the OKF :class:`Embedder` protocol."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client
        self.name: str = (
            getattr(client, "model", None)
            or getattr(client, "DEFAULT_MODEL", None)
            or "fake"
        )
        raw_dim = getattr(client, "embed_dim", None) or getattr(client, "dim", 768)
        self.dim: int = int(raw_dim or 768)

    @classmethod
    def from_default(cls) -> LLMEmbedder:
        return cls(get_llm_client())

    def embed(self, text: str) -> list[float]:
        coro = self._client.embed([text], model="auto")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            vectors = asyncio.run(coro)
        else:  # pragma: no cover - defensive: callers run from async
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            vectors = future.result()
        if not vectors:
            return [0.0] * self.dim
        return list(vectors[0])


__all__ = ["LLMEmbedder"]
