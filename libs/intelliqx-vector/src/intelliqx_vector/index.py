"""Vector index interface and in-memory implementation.

The :class:`VectorIndex` is declared as a :class:`Protocol` (not an
ABC) so structural typing wins: any class with the right methods is a
valid vector index without inheriting from anything. The runtime
type-checker (mypy) uses the Protocol to verify adapters.

The :class:`InMemoryVectorIndex` is the reference implementation. It
L2-normalises vectors at search time (not at insert time) so inserts
are cheap. Queries are O(n · d) per call — fine for n < 50k; beyond
that, use :class:`ZvecIndex`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field


class VectorDoc(BaseModel):
    """A vector document.

    Attributes:
        id: Unique identifier (e.g. ULID).
        tenant_id: Owning tenant. Used to scope search results.
        text: Optional source text. Kept alongside the embedding so
            RAG agents can surface the document without an extra
            fetch.
        vector: The embedding. Length must equal ``VectorIndex.dim``.
        metadata: Free-form label dict. Used for pre-filtering
            (``filter_metadata=...``).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    tenant_id: str
    text: str | None = None
    vector: list[float] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """A single search hit.

    Attributes:
        id: Vector id of the hit.
        score: Cosine similarity in ``[-1, 1]`` (1.0 = identical).
        metadata: The metadata blob stored with the hit.
        text: The hit's source text (if it was indexed).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    text: str | None = None


class VectorIndex(Protocol):
    """Vector index protocol.

    The Protocol is structural: any class implementing these methods
    is a valid vector index, no inheritance required. We use
    ``@property dim`` rather than an instance attribute so derived
    attributes can't be reassigned by accident.
    """

    @property
    def dim(self) -> int:
        """Embedding dimension expected by this index."""
        ...

    async def upsert(self, docs: Sequence[VectorDoc]) -> int:
        """Insert or update documents.

        Returns:
            The number of documents actually written.
        """
        ...

    async def delete(self, ids: Sequence[str]) -> int:
        """Remove documents by id.

        Returns:
            The number of documents actually removed.
        """
        ...

    async def search(
        self,
        vector: list[float],
        *,
        top_k: int = 10,
        tenant_id: str | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Return the top-k most similar documents.

        Args:
            vector: Query embedding. Must equal ``self.dim``.
            top_k: Maximum number of hits to return.
            tenant_id: If set, only documents with this tenant id
                are considered.
            filter_metadata: Optional pre-filter on document
                metadata. All key/value pairs must match exactly.

        Returns:
            Hits sorted by descending score.
        """
        ...

    async def count(self, tenant_id: str | None = None) -> int:
        """Return the number of indexed documents (optionally per-tenant)."""
        ...


class InMemoryVectorIndex:
    """In-process vector index using numpy.

    Used for tests and for low-cardinality datasets that don't
    justify the on-disk index. The implementation is intentionally
    simple and dependency-light: only numpy.

    Complexity:
        * ``upsert`` / ``delete``: O(n) where n is the number of docs.
        * ``search``: O(n · d) per call (brute-force cosine). Fine
          for n < 50k and d < 2k.
    """

    def __init__(self, dim: int) -> None:
        self._dim = dim
        # id -> VectorDoc
        self._docs: dict[str, VectorDoc] = {}

    @property
    def dim(self) -> int:
        return self._dim

    async def upsert(self, docs: Sequence[VectorDoc]) -> int:
        added = 0
        for d in docs:
            if len(d.vector) != self._dim:
                raise ValueError(
                    f"Vector dim mismatch: expected {self._dim}, got {len(d.vector)}"
                )
            self._docs[d.id] = d
            added += 1
        return added

    async def delete(self, ids: Sequence[str]) -> int:
        removed = 0
        for i in ids:
            if i in self._docs:
                del self._docs[i]
                removed += 1
        return removed

    async def search(
        self,
        vector: list[float],
        *,
        top_k: int = 10,
        tenant_id: str | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        if len(vector) != self._dim:
            raise ValueError(f"Vector dim mismatch: expected {self._dim}, got {len(vector)}")

        # First filter: drop candidates that don't match tenant or
        # metadata pre-filters. The expensive part (cosine sim) only
        # runs on the survivors.
        candidates: list[VectorDoc] = []
        for d in self._docs.values():
            if tenant_id is not None and d.tenant_id != tenant_id:
                continue
            if filter_metadata:
                ok = True
                for k, v in filter_metadata.items():
                    if d.metadata.get(k) != v:
                        ok = False
                        break
                if not ok:
                    continue
            candidates.append(d)
        if not candidates:
            return []

        # L2-normalise once per call. The small epsilon avoids 0/0
        # for zero vectors.
        mat = np.array([d.vector for d in candidates], dtype=np.float32)
        q = np.array(vector, dtype=np.float32)
        mat_n = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12)
        q_n = q / (np.linalg.norm(q) + 1e-12)
        sims = mat_n @ q_n
        # ``argsort`` returns ascending; negate to get descending
        # order. ``top_k`` is clamped to the candidate count to
        # avoid an out-of-range slice.
        top_k = min(top_k, len(candidates))
        idx = np.argsort(-sims)[:top_k]
        return [
            SearchResult(
                id=candidates[i].id,
                score=float(sims[i]),
                metadata=candidates[i].metadata,
                text=candidates[i].text,
            )
            for i in idx
        ]

    async def count(self, tenant_id: str | None = None) -> int:
        if tenant_id is None:
            return len(self._docs)
        return sum(1 for d in self._docs.values() if d.tenant_id == tenant_id)


_INSTANCE: VectorIndex | None = None


def get_vector_index() -> VectorIndex:
    """Return the singleton vector index.

    Defaults to a 768-dimensional in-memory index (the size IntelliqX uses
    for most embedding models). Production should construct a
    :class:`ZvecIndex` once at startup and call :func:`set_vector_index`.
    """
    global _INSTANCE
    if _INSTANCE is None:
        import os

        dim = int(os.environ.get("INTELLIQX_VECTOR_DIM", "768"))
        _INSTANCE = InMemoryVectorIndex(dim=dim)
    return _INSTANCE


def set_vector_index(idx: VectorIndex) -> None:
    """Replace the singleton vector index.

    Used by application bootstrap to install a configured
    :class:`ZvecIndex` (or any other ``VectorIndex`` implementation)
    before the first ``get_vector_index`` call.
    """
    global _INSTANCE
    _INSTANCE = idx


def reset_vector_index() -> None:
    """Clear the singleton (for tests)."""
    global _INSTANCE
    _INSTANCE = None
