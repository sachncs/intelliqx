"""Embedder contract used by the OKF index.

The contract is intentionally small: an embedder is identified by
``name`` + ``dim`` and produces a single vector for one string. The
index records ``name`` and ``dim`` on creation and refuses to reopen
against a different combination, so a model swap requires an explicit
rebuild rather than silently corrupting retrieval.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, text: str) -> list[float]: ...


class EmbeddingMismatchError(ValueError):
    """Raised when the existing index was built with a different embedder."""

    def __init__(
        self, *, existing_name: str, existing_dim: int, requested_name: str, requested_dim: int
    ) -> None:
        super().__init__(
            f"Index was built with embedder={existing_name!r} dim={existing_dim}; "
            f"requested embedder={requested_name!r} dim={requested_dim}"
        )
        self.existing_name = existing_name
        self.existing_dim = existing_dim
        self.requested_name = requested_name
        self.requested_dim = requested_dim


__all__ = ["Embedder", "EmbeddingMismatchError"]
