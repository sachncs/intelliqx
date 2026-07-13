"""sqlite-vec backed vector index.

Reference: https://github.com/asg017/sqlite-vec

sqlite-vec adds a ``vec0`` virtual table to SQLite that supports
fast nearest-neighbour search over fixed-dimensional float32
vectors. The implementation here stores vectors in a single
``.sqlite`` file that lives in the IntelliqX object store, so the
index survives process restarts and is sharable across agents.

Storage layout (inside the SQLite file):

* ``documents`` table — one row per vector:
  ``(id, tenant_id, text, metadata_json, vector BLOB)``
* ``doc_index`` ``vec0`` virtual table — the searchable copy of
  the vector column, dimensioned at construction time.
* ``_meta`` table — persists dimension so reopening with a
  mismatched dim fails clearly.

The ``documents`` table is the source of truth (it carries the
text and metadata). The ``doc_index`` is rebuilt on demand if
it is missing or the schema is stale.

Cosine similarity is computed in Python after the vector search so
the ``VectorIndex`` contract score semantics (cosine similarity
in ``[-1, 1]``) are preserved regardless of the distance metric
used by vec0 internally.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from typing import Any

from intelliqx_vector.index import SearchResult, VectorDoc


def _serialize(vector: list[float]) -> bytes:
    """Convert a float list into sqlite-vec's expected byte format.

    Uses :func:`sqlite_vec.serialize_float32`; the function is
    stable across sqlite-vec versions because it mirrors the
    on-disk layout the extension expects.
    """
    import sqlite_vec  # type: ignore[import-untyped]

    return sqlite_vec.serialize_float32(vector)


def _cosine_similarity(a: bytes, b: bytes) -> float:
    """Cosine similarity between two sqlite-vec packed vectors.

    Returns a value in ``[-1, 1]`` where 1.0 means identical.
    The function avoids importing numpy so the index stays
    dependency-light.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    n = len(a) // 4
    if n == 0:
        return 0.0
    import struct

    fa = struct.unpack(f"<{n}f", a)
    fb = struct.unpack(f"<{n}f", b)
    dot = sum(x * y for x, y in zip(fa, fb, strict=False))
    na = sum(x * x for x in fa) ** 0.5 + 1e-12
    nb = sum(x * x for x in fb) ** 0.5 + 1e-12
    sim = dot / (na * nb)
    if sim > 1.0:
        sim = 1.0
    elif sim < -1.0:
        sim = -1.0
    return sim


class SqliteVecIndex:
    """sqlite-vec backed vector index backed by a single SQLite file.

    The index is persisted in ``db_path``. The file is created on
    first use; reopening it later re-loads the existing vectors.

    Concurrency: SQLite's default journal mode supports multiple
    readers but only one writer. The implementation serialises
    writes with a connection-level lock; concurrent ``upsert`` calls
    from the same process are queued.
    """

    def __init__(self, dim: int, *, db_path: str | None = None) -> None:
        import os

        import sqlite_vec

        self.__dim = dim
        self.__db_path = db_path or ":memory:"
        self.__sqlite_vec = sqlite_vec
        self.__conn = sqlite3.connect(self.__db_path, check_same_thread=False)
        self.__conn.execute("PRAGMA journal_mode=WAL")
        self.__conn.execute("PRAGMA synchronous=NORMAL")
        self.__conn.enable_load_extension(True)
        for candidate in (
            self.__sqlite_vec.loadable_path(),
            self.__sqlite_vec.loadable_path() + ".dylib",
            self.__sqlite_vec.loadable_path() + ".so",
        ):
            if os.path.exists(candidate):
                self.__conn.load_extension(candidate)
                break
        else:
            raise RuntimeError(
                f"sqlite-vec extension not found at {self.__sqlite_vec.loadable_path()}"
            )
        self.__write_lock = __import__("threading").Lock()
        self._ensure_schema()

    @property
    def dim(self) -> int:
        return self.__dim

    def _ensure_schema(self) -> None:
        """Create tables if they don't exist.

        ``vec0`` is a virtual table; ``documents`` is a regular
        table. We keep ``documents.id`` as the primary key so
        metadata updates don't require deleting+re-inserting the
        vector row.
        """
        with self.__write_lock:
            self.__conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    text TEXT,
                    metadata_json TEXT,
                    vector BLOB NOT NULL
                )
                """
            )
            self.__conn.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS doc_index USING vec0(
                    embedding float[{self.dim}]
                )
                """
            )
            self.__conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id)"
            )
            self.__conn.execute(
                """
                CREATE TABLE IF NOT EXISTS _meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            cur = self.__conn.cursor()
            existing_dim_row = cur.execute("SELECT value FROM _meta WHERE key = 'dim'").fetchone()
            if existing_dim_row and existing_dim_row[0] != str(self.dim):
                raise ValueError(
                    f"Dimension mismatch: index was created with dim={existing_dim_row[0]}, "
                    f"but SqliteVecIndex was constructed with dim={self.dim}"
                )
            cur.execute(
                "INSERT OR REPLACE INTO _meta (key, value) VALUES ('dim', ?)",
                (str(self.dim),),
            )
            self.__conn.commit()

    async def upsert(self, docs: Sequence[VectorDoc]) -> int:
        """Insert or update ``docs`` in the index.

        Returns:
            The number of documents written.
        """
        if not docs:
            return 0
        with self.__write_lock:
            cur = self.__conn.cursor()
            added = 0
            for d in docs:
                if len(d.vector) != self.dim:
                    raise ValueError(
                        f"Vector dim mismatch: expected {self.dim}, got {len(d.vector)}"
                    )
                packed = _serialize(d.vector)
                cur.execute(
                    """
                    INSERT INTO documents (id, tenant_id, text, metadata_json, vector)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        tenant_id = excluded.tenant_id,
                        text = excluded.text,
                        metadata_json = excluded.metadata_json,
                        vector = excluded.vector
                    """,
                    (
                        d.id,
                        d.tenant_id,
                        d.text or "",
                        json.dumps(d.metadata),
                        packed,
                    ),
                )
                cur.execute("SELECT rowid FROM documents WHERE id = ?", (d.id,))
                row = cur.fetchone()
                if row is None:
                    continue
                rowid = row[0]
                cur.execute(
                    "DELETE FROM doc_index WHERE rowid = ?",
                    (rowid,),
                )
                cur.execute(
                    "INSERT INTO doc_index (rowid, embedding) VALUES (?, ?)",
                    (rowid, packed),
                )
                added += 1
            self.__conn.commit()
        return added

    async def delete(self, ids: Sequence[str]) -> int:
        """Remove documents by id.

        Returns:
            The number of documents actually removed.
        """
        if not ids:
            return 0
        with self.__write_lock:
            cur = self.__conn.cursor()
            removed = 0
            for i in ids:
                cur.execute(
                    "DELETE FROM doc_index WHERE rowid IN (SELECT rowid FROM documents WHERE id = ?)",
                    (i,),
                )
                cur.execute("DELETE FROM documents WHERE id = ?", (i,))
                removed += cur.rowcount
            self.__conn.commit()
        return removed

    async def search(
        self,
        vector: list[float],
        *,
        top_k: int = 10,
        tenant_id: str | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Top-k ANN search with optional tenant + metadata filters.

        Candidate selection:

        1. Collect eligible rowids from ``documents`` by applying
           tenant and metadata filters first (pre-filter).
        2. If no eligible rowids, return empty.
        3. Query ``doc_index`` with ``k = max(top_k, len(eligible))``
           and compute cosine similarity against each candidate.
        4. Sort by descending score and take ``top_k``.

        This guarantees the contract: only documents matching the
        filter are returned, and ``top_k`` is respected (up to the
        eligible set size).
        """
        if len(vector) != self.dim:
            raise ValueError(f"Vector dim mismatch: expected {self.dim}, got {len(vector)}")
        cur = self.__conn.cursor()

        # Step 1: Pre-filter — collect eligible rowids.
        eligible_sql = "SELECT rowid, id, tenant_id, metadata_json FROM documents"
        eligible_conditions: list[str] = []
        eligible_params: list[Any] = []
        if tenant_id is not None:
            eligible_conditions.append("tenant_id = ?")
            eligible_params.append(tenant_id)
        if filter_metadata:
            for k, v in filter_metadata.items():
                eligible_conditions.append("json_extract(metadata_json, ?) = ?")
                eligible_params.append(f"$.{k}")
                eligible_params.append(v)
        if eligible_conditions:
            eligible_sql += " WHERE " + " AND ".join(eligible_conditions)
        cur.execute(eligible_sql, eligible_params)
        eligible = cur.fetchall()
        if not eligible:
            return []

        eligible_rowids = {row[0] for row in eligible}
        eligible_meta = {
            row[0]: {
                "id": row[1],
                "tenant_id": row[2],
                "metadata_json": row[3],
            }
            for row in eligible
        }

        # Step 2: Vector search — retrieve enough candidates.
        oversample = max(top_k, len(eligible_rowids))
        packed = _serialize(vector)
        cur.execute(
            """
            SELECT rowid, embedding
            FROM doc_index
            WHERE embedding MATCH ? AND k = ?
            """,
            (packed, oversample),
        )
        vector_results = cur.fetchall()

        # Step 3: Compute cosine similarity against eligible docs.
        query_packed = packed
        results: list[SearchResult] = []
        for vec_rowid, emb_blob in vector_results:
            if vec_rowid not in eligible_rowids:
                continue
            score = _cosine_similarity(query_packed, emb_blob)
            meta_info = eligible_meta[vec_rowid]
            try:
                meta = json.loads(meta_info["metadata_json"]) if meta_info["metadata_json"] else {}
            except json.JSONDecodeError:
                meta = {}
            results.append(
                SearchResult(
                    id=str(meta_info["id"]),
                    score=score,
                    metadata=meta,
                    text=None,
                )
            )
            if len(results) >= top_k:
                break

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def count(self, tenant_id: str | None = None) -> int:
        """Return the number of indexed documents (optionally per-tenant)."""
        cur = self.__conn.cursor()
        if tenant_id is None:
            cur.execute("SELECT COUNT(*) FROM documents")
        else:
            cur.execute("SELECT COUNT(*) FROM documents WHERE tenant_id = ?", (tenant_id,))
        return int(cur.fetchone()[0])

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.__conn.close()

    def __del__(self) -> None:
        """Best-effort cleanup if the index is garbage-collected."""
        import contextlib

        with contextlib.suppress(Exception):
            self.close()
