"""Pydaxis-AI-backed :class:`Embedder` adapter for the OKF vector path.

The production embedder wraps a Pydaxis-AI ``EmbeddingModel`` returned
by :func:`intelliqx_ai.runtime.build_embedder`. The OKF ``Index`` only
calls the sync :meth:`Embedder.embed` contract; the Pydaxis-AI
``EmbeddingModel.embed`` method is async, so we drive it from the
current running loop when present and via ``asyncio.run`` otherwise.
Tests pass a :class:`FakeEmbedder` (from :mod:`tests.okf._embed`)
which does not depend on a network.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from intelliqx_ai.runtime import build_embedder
from intelliqx_okf.embed import Embedder

if TYPE_CHECKING:
    from pydantic_ai.embeddings import EmbeddingModel


class PydaxisAIEmbedder(Embedder):
    """Adapt a Pydaxis-AI :class:`EmbeddingModel` to the OKF :class:`Embedder` protocol."""

    def __init__(self, model: "EmbeddingModel | None" = None, *, name: str = "pydaxis-ai") -> None:
        self._model = model if model is not None else build_embedder()
        self.name = name
        # ``model.max_input_tokens`` is the supported Pydaxis-AI hook
        # for the size limit; we keep it as a class attribute and read
        # lazily because the embedder can be patched in tests.
        self.dim = int(getattr(self._model, "dimensions", 0) or 0)

    @classmethod
    def from_default(cls) -> "PydaxisAIEmbedder":
        """Build the production Pydaxis-AI embedding model for the OKF vector path."""
        return cls(build_embedder())

    def embed(self, text: str) -> list[float]:
        """Return the embedding vector for a single text string."""
        coro = self._model.embed(text, input_type="document")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            result = asyncio.run(coro)
        else:
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            result = future.result()
        return list(result.embeddings[0])


__all__ = ["PydaxisAIEmbedder"]