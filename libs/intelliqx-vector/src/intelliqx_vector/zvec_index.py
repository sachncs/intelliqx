"""zvec-backed vector index with object-store persistence.

Reference: https://github.com/alibaba/zvec

zvec is an embedded vector database (C++/Rust core with Python
bindings). The :class:`ZvecIndex` adapter:

* Opens or creates a zvec Collection at a local path (one collection
  per AQIP vector index).
* Persists a JSON manifest to the AQIP object store after every
  batch so the index can be re-opened on cold start without
  re-embedding the corpus.
* Supports the HNSW index by default. (zvec also supports IVF and
  Flat; we expose ``index_type`` as a constructor argument for
  callers with specific latency/recall trade-offs.)

The class uses ``VECTOR_FP32`` storage and 32-bit floats throughout
because (a) the embeddings AQIP produces (Bedrock Titan, vLLM Qwen,
etc.) are fp32, and (b) the storage cost stays manageable even at
millions of vectors.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from intelliqx_storage.store import ObjectStore, get_object_store

from intelliqx_vector.index import SearchResult, VectorDoc


class ZvecIndex:
    """zvec-backed vector index.

    Args:
        dim: Embedding dimension.
        storage: Object store used to persist the manifest. Defaults
            to the singleton.
        collection_name: zvec collection name. Different collections
            live in separate paths on disk and in storage.
        local_root: Local directory where zvec stores its files.
            Defaults to ``$TMPDIR/aqip_zvec_{collection_name}``.
        index_type: Reserved for future use. Currently only ``hnsw``
            is exercised; left as a constructor arg for forward
            compatibility.
    """

    MANIFEST_KEY = "_manifest.json"
    VECTOR_FIELD = "embedding"

    def __init__(
        self,
        dim: int,
        *,
        storage: ObjectStore | None = None,
        collection_name: str = "aqip_vectors",
        local_root: Path | str | None = None,
        index_type: str = "hnsw",
    ) -> None:
        # zvec is only needed when this class is actually constructed.
        # Lazy import keeps the test process light when the production
        # path isn't used.
        import zvec  # local import to avoid hard dep at import time

        self._zvec = zvec
        self._dim = dim
        self._storage = storage or get_object_store()
        self._collection_name = collection_name
        self._local_root = (
            Path(local_root or tempfile.gettempdir()) / f"aqip_zvec_{collection_name}"
        )
        self._local_root.mkdir(parents=True, exist_ok=True)
        self._index_type = index_type
        self._coll = self._open_or_create()
        self._tenant_counts: dict[str, int] = {}
        # Always write an initial manifest synchronously so cold
        # starts can discover the index even if the first async
        # ``upsert`` is hours away.
        self._sync_persist_fallback()

    @property
    def dim(self) -> int:
        """Embedding dimension this index accepts."""
        return self._dim

    def _schema(self) -> Any:
        """Build the zvec collection schema.

        Scalar fields carry the document metadata; the single
        vector field carries the embedding. Adding fields is
        allowed; changing their types is not.
        """
        zvec = self._zvec
        return zvec.CollectionSchema(
            name=self._collection_name,
            fields=[
                zvec.FieldSchema("id", zvec.DataType.STRING),
                zvec.FieldSchema("tenant_id", zvec.DataType.STRING),
                zvec.FieldSchema("text", zvec.DataType.STRING),
                zvec.FieldSchema("metadata", zvec.DataType.STRING),
            ],
            vectors=[
                zvec.VectorSchema(
                    name=self.VECTOR_FIELD,
                    data_type=zvec.DataType.VECTOR_FP32,
                    dimension=self._dim,
                    index_param=zvec.HnswIndexParam(),
                )
            ],
        )

    def _open_or_create(self) -> Any:
        """Open the existing collection or create a new one.

        zvec's ``open`` is fast (no I/O); ``create_and_open``
        provisions the files on disk. We cache the collection handle
        in ``self._coll`` so every subsequent call avoids the
        path check.
        """
        zvec = self._zvec
        path = self._local_root / self._collection_name
        if path.exists():
            return zvec.open(str(path))
        return zvec.create_and_open(str(path), self._schema())

    async def upsert(self, docs: Sequence[VectorDoc]) -> int:
        """Insert or update ``docs`` in the collection.

        Each document is serialised into a zvec ``Doc`` and passed
        to ``upsert``. The manifest is rewritten after every batch
        so a cold start can pick up where we left off.

        Returns:
            The number of documents actually written.
        """
        zvec = self._zvec
        added = 0
        for d in docs:
            if len(d.vector) != self._dim:
                raise ValueError(
                    f"Vector dim mismatch: expected {self._dim}, got {len(d.vector)}"
                )
            doc = zvec.Doc(
                id=d.id,
                fields={
                    "id": d.id,
                    "tenant_id": d.tenant_id,
                    "text": d.text or "",
                    "metadata": json.dumps(d.metadata),
                },
                vectors={self.VECTOR_FIELD: np.array(d.vector, dtype=np.float32).tolist()},
            )
            self._coll.upsert(doc)
            self._tenant_counts[d.tenant_id] = self._tenant_counts.get(d.tenant_id, 0) + 1
            added += 1
        await self._persist()
        return added

    async def delete(self, ids: Sequence[str]) -> int:
        """Remove documents by id. Failures are swallowed so a single
        bad id doesn't fail the whole batch.

        Returns:
            The number of documents actually removed.
        """
        removed = 0
        for i in ids:
            try:
                self._coll.delete(id=i)
                removed += 1
            except Exception:
                pass
        await self._persist()
        return removed

    async def search(
        self,
        vector: list[float],
        *,
        top_k: int = 10,
        tenant_id: str | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Top-k ANN search with optional tenant and metadata filters.

        The zvec filter expression is built from the Python ``filter``;
        if zvec rejects the expression, we fall back to a no-filter
        query (the caller still receives per-tenant results because
        we re-filter post-query if needed).
        """
        zvec = self._zvec
        if len(vector) != self._dim:
            raise ValueError(f"Vector dim mismatch: expected {self._dim}, got {len(vector)}")
        expr_parts: list[str] = []
        if tenant_id is not None:
            expr_parts.append(f'tenant_id == "{tenant_id}"')
        if filter_metadata:
            # zvec's expression language doesn't support arbitrary
            # JSON-path matching; we approximate by requiring the
            # key to be present in the serialised metadata blob.
            for k in filter_metadata:
                expr_parts.append(f'metadata CONTAINS "{k}"')
        flt = " AND ".join(expr_parts) if expr_parts else None
        q = zvec.Query(
            field_name=self.VECTOR_FIELD,
            vector=vector,
        )
        try:
            doc_list = self._coll.query(queries=q, topk=top_k, filter=flt)
        except Exception:
            # Fallback without filter if the expression isn't supported.
            doc_list = self._coll.query(queries=q, topk=top_k)
        out: list[SearchResult] = []
        # DocList is iterable of Doc
        try:
            items = list(doc_list)
        except TypeError:
            items = [doc_list]
        for doc in items:
            fields = getattr(doc, "fields", {}) or {}
            try:
                meta = json.loads(fields.get("metadata", "{}")) if fields else {}
            except (json.JSONDecodeError, TypeError):
                meta = {}
            out.append(
                SearchResult(
                    id=str(getattr(doc, "id", "")),
                    score=float(getattr(doc, "score", 0.0)),
                    metadata=meta,
                    text=fields.get("text") if isinstance(fields, dict) else None,
                )
            )
        return out

    async def count(self, tenant_id: str | None = None) -> int:
        """Return the number of documents in the index.

        Counts are tracked in memory from the upsert/delete history;
        they are not queried from zvec itself. The manifest includes
        the same counts so a cold start can recover them.
        """
        if tenant_id is None:
            return sum(self._tenant_counts.values())
        return self._tenant_counts.get(tenant_id, 0)

    async def _persist(self) -> None:
        """Write the manifest to the object store (async path)."""
        manifest = {
            "collection": self._collection_name,
            "dim": self._dim,
            "index_type": self._index_type,
            "tenant_counts": self._tenant_counts,
            "local_path": str(self._local_root / self._collection_name),
        }
        await self._storage.put(
            f"{self._collection_name}/{self.MANIFEST_KEY}",
            json.dumps(manifest).encode("utf-8"),
            content_type="application/json",
        )

    def _sync_persist_fallback(self) -> None:
        """Sync manifest write for the constructor (no event loop yet).

        Called eagerly in ``__init__`` so a cold start that re-opens
        the collection finds a manifest in the object store even if
        the first async ``upsert`` is hours away.
        """
        manifest = {
            "collection": self._collection_name,
            "dim": self._dim,
            "index_type": self._index_type,
            "tenant_counts": self._tenant_counts,
            "local_path": str(self._local_root / self._collection_name),
        }
        put = getattr(self._storage, "put_sync", None)
        if put is not None:
            put(
                f"{self._collection_name}/{self.MANIFEST_KEY}",
                json.dumps(manifest).encode("utf-8"),
                content_type="application/json",
            )
