"""SQLite-backed OKF catalog with tenant scoping.

Combines the OKF format with a SQLite catalog so the platform can
answer "give me all ``API Endpoint`` concepts tagged ``payments``
updated after 2026-01-01, ranked by full-text relevance to a query"
in a single query.

The catalog is built on top of :class:`OKFBundle`: load a bundle,
then ``build_catalog`` to ingest every concept into a single
SQLite database. The schema:

* ``concepts`` — one row per concept, with the OKF frontmatter
  fields projected into typed columns plus the raw body and a
  ``tenant_id`` column for multi-tenant scoping.
* ``concepts_fts`` — FTS5 virtual table over the title,
  description, and body for full-text search.
* ``concepts_ai`` — sqlite-vec ``vec0`` table holding the embedding
  of every concept that has one. Joins with ``concepts`` on
  ``concept_id`` for hybrid retrieval.

Retrieval pipeline:

1. **Structured filter** — ``tenant_id = ? AND type IN (...) AND
   tags ? ?1`` returns a candidate set.
2. **Dual candidate generation** — FTS5 candidates and vector
   candidates are generated independently (both constrained by the
   structured filter), then unioned.
3. **Rank fusion** — reciprocal-rank fusion (RRF) merges the two
   ranked lists into a single score.
4. **Optional vector boost** — when embeddings are present, the
   combined score blends RRF score with cosine similarity.

The class is in-process; the SQLite file lives in the IntelliqX
object store so the catalog survives process restarts.

RRF algorithm (mathematical description):

Reciprocal-rank fusion combines two independently ranked lists
(FTS5 and vector) into a single score per candidate. Given a
constant ``k = 60`` (the ``RRF_K`` parameter), the RRF score
for a candidate at rank ``r`` (0-indexed) in a list is::

    rrf_score = 1 / (k + r + 1)

The two lists are weighted by ``vector_weight`` (``w``). The
final RRF score for a candidate is::

    score(c) = (1 - w) * sum(1/(k + r_fts + 1))  +  w * sum(1/(k + r_vec + 1))

where ``r_fts`` and ``r_vec`` are the candidate's ranks in the
FTS5 and vector lists respectively. A candidate that appears in
only one list gets a non-zero score from that list alone. When
neither list contributed any ranked results, all candidates
receive a base score of ``1/k``.

The constant ``k = 60`` is the standard value from the original
RRF paper (Cormack et al., SIGIR 2009) and balances the
contribution of top-ranked vs. lower-ranked results.
"""

from __future__ import annotations

import json
import re
import sqlite3
import struct
from dataclasses import dataclass
from typing import Any

from intelliqx_okf.bundle import OKFBundle

RRF_K = 60  # Constant for reciprocal-rank fusion.


def pack_floats(vector: list[float]) -> bytes:
    """Pack a Python ``list[float]`` into the byte string sqlite-vec expects.

    Uses 4 bytes per float (little-endian, IEEE-754). Equivalent to
    ``numpy.array(vector, dtype=\"<f4\").tobytes()`` but dependency-
    free.
    """
    return struct.pack(f"<{len(vector)}f", *vector)


def tokenize_fts5(query: str) -> str:
    """Safely convert a natural-language query into an FTS5 expression.

    Extracts alphanumeric tokens (stripping punctuation), quotes each
    one, and joins them with ``AND``.  This prevents FTS5 syntax
    errors from hyphens, question marks, quotes, and other punctuation
    that users naturally include in queries.

    Examples::

        >>> tokenize_fts5("hello-world")
        '"hello" AND "world"'
        >>> tokenize_fts5("how do I test?")
        '"how" AND "do" AND "I" AND "test"'
        >>> tokenize_fts5('"quoted" phrase')
        '"quoted" AND "phrase"'
    """
    tokens = re.findall(r"[A-Za-z0-9]+", query)
    if not tokens:
        return ""
    return " AND ".join(f'"{t}"' for t in tokens)


@dataclass
class CatalogHit:
    """A single hit from :meth:`OKFCatalog.search`.

    All fields after ``score`` are optional. The dataclass
    declaration order is significant: required fields first, then
    defaulted ones.
    """

    concept_id: str
    type: str
    title: str | None
    description: str | None
    score: float
    tags: list[str]
    timestamp: str | None
    snippet: str
    fts_score: float = 0.0
    vector_score: float = 0.0


class OKFCatalog:
    """SQLite-backed OKF catalog with optional sqlite-vec embeddings.

    The catalog stores a single SQLite file (``db_path``). On
    ``build_catalog`` it wipes the existing content for the given
    tenant and re-ingests; on ``search`` it runs the structured
    filter + dual-candidate FTS/vector RRF pipeline.
    """

    def __init__(self, db_path: str | None = None, *, dim: int | None = None) -> None:
        self.db_path = db_path or ":memory:"
        self.dim = dim
        self.sqlite_vec = None
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
            self.conn.execute("DROP TABLE _fts5_probe")
            self.has_fts5 = True
        except sqlite3.OperationalError:
            self.has_fts5 = False
        if self.dim is not None:
            try:
                import os

                import sqlite_vec  # type: ignore[import-untyped]

                self.sqlite_vec = sqlite_vec
                self.conn.enable_load_extension(True)
                for candidate in (
                    sqlite_vec.loadable_path(),
                    sqlite_vec.loadable_path() + ".dylib",
                    sqlite_vec.loadable_path() + ".so",
                ):
                    if os.path.exists(candidate):
                        self.conn.load_extension(candidate)
                        break
                self.conn.execute(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS concepts_ai USING vec0(embedding float[{self.dim}])"
                )
            except Exception:
                self.sqlite_vec = None
        self.ensure_schema()

    def ensure_schema(self) -> None:
        """Create the catalog tables if they don't exist."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS concepts (
                concept_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL DEFAULT '_global',
                type TEXT NOT NULL,
                title TEXT,
                description TEXT,
                body TEXT,
                tags_json TEXT,
                timestamp TEXT,
                resource TEXT,
                metadata_json TEXT,
                source_path TEXT,
                PRIMARY KEY (concept_id, tenant_id)
            )
            """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_concepts_type ON concepts(type)")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_concepts_timestamp ON concepts(timestamp)"
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_concepts_tenant ON concepts(tenant_id)")
        if self.has_fts5:
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS concepts_fts USING fts5(
                    concept_id,
                    tenant_id,
                    title,
                    description,
                    body,
                    tokenize = 'porter unicode61'
                )
                """)
        self.conn.commit()

    def build_catalog(
        self, bundle: OKFBundle, *, tenant_id: str = "_global", reserve_reserved: bool = False
    ) -> int:
        """Ingest concepts from ``bundle`` for a specific tenant.

        Wipes existing content for the given tenant only, so
        concurrent tenants are not disrupted.

        Args:
            bundle: The loaded OKF bundle.
            tenant_id: Tenant scope for the ingested concepts.
            reserve_reserved: If ``False`` (default), skip reserved
                concepts (``index.md``, ``log.md``) in the catalog.

        Returns:
            The number of concepts ingested.
        """
        self.conn.execute("DELETE FROM concepts WHERE tenant_id = ?", (tenant_id,))
        if self.has_fts5:
            self.conn.execute("DELETE FROM concepts_fts WHERE tenant_id = ?", (tenant_id,))
        if self.sqlite_vec is not None:
            self.conn.execute(
                """
                DELETE FROM concepts_ai WHERE rowid IN (
                    SELECT rowid FROM concepts WHERE tenant_id = ?
                )
                """,
                (tenant_id,),
            )
        cur = self.conn.cursor()
        count = 0
        for concept in bundle.concepts.values():
            if not reserve_reserved and concept.concept_id in bundle.reserved:
                continue
            cur.execute(
                """
                INSERT OR REPLACE INTO concepts
                  (concept_id, tenant_id, type, title, description, body,
                   tags_json, timestamp, resource, metadata_json, source_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    concept.concept_id,
                    tenant_id,
                    concept.frontmatter.type,
                    concept.frontmatter.title,
                    concept.frontmatter.description,
                    concept.body,
                    json.dumps(concept.frontmatter.tags or []),
                    (
                        concept.frontmatter.timestamp.isoformat()
                        if concept.frontmatter.timestamp
                        else None
                    ),
                    concept.frontmatter.resource,
                    json.dumps(concept.frontmatter.extra_fields),
                    str(concept.source_path) if concept.source_path else None,
                ),
            )
            if self.has_fts5:
                cur.execute(
                    """
                    INSERT INTO concepts_fts (concept_id, tenant_id, title, description, body)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        concept.concept_id,
                        tenant_id,
                        concept.frontmatter.title or "",
                        concept.frontmatter.description or "",
                        concept.body or "",
                    ),
                )
            count += 1
        self.conn.commit()
        return count

    def store_embedding(
        self, concept_id: str, vector: list[float], *, tenant_id: str = "_global"
    ) -> None:
        """Upsert an embedding for ``concept_id`` within a tenant scope."""
        if self.sqlite_vec is None:
            return
        if self.dim is not None and len(vector) != self.dim:
            raise ValueError(f"Vector dim mismatch: expected {self.dim}, got {len(vector)}")
        cur = self.conn.cursor()
        cur.execute(
            "SELECT rowid FROM concepts WHERE concept_id = ? AND tenant_id = ?",
            (concept_id, tenant_id),
        )
        row = cur.fetchone()
        if row is None:
            return
        rowid = row[0]
        cur.execute("DELETE FROM concepts_ai WHERE rowid = ?", (rowid,))
        cur.execute(
            "INSERT INTO concepts_ai (rowid, embedding) VALUES (?, ?)", (rowid, pack_floats(vector))
        )
        self.conn.commit()

    def list_types(self, *, tenant_id: str | None = None) -> list[str]:
        """Return the distinct ``type`` values present in the catalog."""
        cur = self.conn.cursor()
        if tenant_id is not None:
            return [
                row[0]
                for row in cur.execute(
                    "SELECT DISTINCT type FROM concepts WHERE tenant_id = ? ORDER BY type",
                    (tenant_id,),
                )
            ]
        return [row[0] for row in cur.execute("SELECT DISTINCT type FROM concepts ORDER BY type")]

    def list_tags(self, *, tenant_id: str | None = None) -> list[str]:
        """Return the distinct tag values present in the catalog."""
        cur = self.conn.cursor()
        out: set[str] = set()
        if tenant_id is not None:
            rows = cur.execute("SELECT tags_json FROM concepts WHERE tenant_id = ?", (tenant_id,))
        else:
            rows = cur.execute("SELECT tags_json FROM concepts")
        for (tags_json,) in rows:
            if not tags_json:
                continue
            try:
                out.update(json.loads(tags_json))
            except json.JSONDecodeError:
                continue
        return sorted(out)

    def structured_where(
        self,
        *,
        table_alias: str = "c",
        tenant_id: str | None = None,
        type_filter: list[str] | None = None,
        tag_filter: list[str] | None = None,
    ) -> tuple[list[str], list[Any]]:
        """Build WHERE clause fragments for structured filtering."""
        conditions: list[str] = []
        params: list[Any] = []
        if tenant_id is not None:
            conditions.append(f"{table_alias}.tenant_id = ?")
            params.append(tenant_id)
        if type_filter:
            placeholders = ",".join("?" * len(type_filter))
            conditions.append(f"{table_alias}.type IN ({placeholders})")
            params.extend(type_filter)
        if tag_filter:
            for tag in tag_filter:
                conditions.append(
                    f"EXISTS (SELECT 1 FROM json_each({table_alias}.tags_json) WHERE value = ?)"
                )
                params.append(tag)
        return conditions, params

    def fetch_fts_candidates(
        self,
        query: str,
        *,
        tenant_id: str | None = None,
        type_filter: list[str] | None = None,
        tag_filter: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve FTS5 candidates constrained by structured filters."""
        if not self.has_fts5 or not query:
            return []
        fts_expr = tokenize_fts5(query)
        if not fts_expr:
            return []
        cur = self.conn.cursor()
        conditions, params = self.structured_where(
            table_alias="c", tenant_id=tenant_id, type_filter=type_filter, tag_filter=tag_filter
        )
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
            SELECT f.concept_id, c.type, c.title, c.description, c.body,
                   c.tags_json, c.timestamp, bm25(concepts_fts) AS fts_score,
                   snippet(concepts_fts, 4, '<b>', '</b>', '…', 16) AS snippet
            FROM concepts_fts f
            JOIN concepts c ON c.concept_id = f.concept_id AND c.tenant_id = f.tenant_id
            WHERE f.tenant_id = ? AND f.concepts_fts MATCH ? AND {where_clause}
            ORDER BY bm25(concepts_fts)
            LIMIT ?
        """
        full_params = [tenant_id or "_global", fts_expr] + params + [limit]
        cur.execute(sql, full_params)
        candidates: list[dict[str, Any]] = []
        for row in cur.fetchall():
            (
                concept_id,
                type_,
                title,
                description,
                body,
                tags_json,
                timestamp,
                fts_score,
                snippet,
            ) = row
            try:
                tags = json.loads(tags_json) if tags_json else []
            except json.JSONDecodeError:
                tags = []
            candidates.append(
                {
                    "concept_id": concept_id,
                    "type": type_,
                    "title": title,
                    "description": description,
                    "body": body,
                    "tags": tags,
                    "timestamp": timestamp,
                    "fts_score": float(fts_score) if fts_score is not None else 0.0,
                    "snippet": snippet or "",
                    "vector_score": 0.0,
                }
            )
        return candidates

    def fetch_structured_candidates(
        self,
        *,
        tenant_id: str | None = None,
        type_filter: list[str] | None = None,
        tag_filter: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve all concepts matching structured filters (no FTS)."""
        cur = self.conn.cursor()
        conditions, params = self.structured_where(
            table_alias="c", tenant_id=tenant_id, type_filter=type_filter, tag_filter=tag_filter
        )
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
            SELECT c.concept_id, c.type, c.title, c.description, c.body,
                   c.tags_json, c.timestamp,
                   substr(c.body, 1, 160) AS snippet
            FROM concepts c
            WHERE {where_clause}
            LIMIT ?
        """
        full_params = params + [limit]
        cur.execute(sql, full_params)
        candidates: list[dict[str, Any]] = []
        for row in cur.fetchall():
            concept_id, type_, title, description, body, tags_json, timestamp, snippet = row
            try:
                tags = json.loads(tags_json) if tags_json else []
            except json.JSONDecodeError:
                tags = []
            candidates.append(
                {
                    "concept_id": concept_id,
                    "type": type_,
                    "title": title,
                    "description": description,
                    "body": body,
                    "tags": tags,
                    "timestamp": timestamp,
                    "fts_score": 0.0,
                    "snippet": snippet or "",
                    "vector_score": 0.0,
                }
            )
        return candidates

    def fetch_vector_candidates(
        self,
        query_embedding: list[float],
        *,
        tenant_id: str | None = None,
        type_filter: list[str] | None = None,
        tag_filter: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve vector candidates constrained by structured filters.

        Collects eligible rowids first, then queries vec0 against
        those rowids.  Computes cosine similarity in Python.
        """
        if self.sqlite_vec is None:
            return []
        cur = self.conn.cursor()
        conditions, params = self.structured_where(
            table_alias="c", tenant_id=tenant_id, type_filter=type_filter, tag_filter=tag_filter
        )
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        cur.execute(
            f"SELECT c.rowid, c.concept_id, c.type, c.title, c.description, c.body, c.tags_json, c.timestamp FROM concepts c WHERE {where_clause}",
            params,
        )
        eligible = cur.fetchall()
        if not eligible:
            return []
        eligible_by_rowid = {
            row[0]: {
                "concept_id": row[1],
                "type": row[2],
                "title": row[3],
                "description": row[4],
                "body": row[5],
                "tags_json": row[6],
                "timestamp": row[7],
            }
            for row in eligible
        }
        packed = pack_floats(query_embedding)
        cur.execute(
            "SELECT rowid, embedding FROM concepts_ai WHERE embedding MATCH ? AND k = ?",
            (packed, max(limit, len(eligible_by_rowid))),
        )
        candidates: list[dict[str, Any]] = []

        n = len(query_embedding)
        q_bytes = packed
        for vec_rowid, emb_blob in cur.fetchall():
            if vec_rowid not in eligible_by_rowid:
                continue
            info = eligible_by_rowid[vec_rowid]
            fb = struct.unpack(f"<{n}f", emb_blob)
            fa = struct.unpack(f"<{n}f", q_bytes)
            dot = sum(x * y for x, y in zip(fa, fb, strict=False))
            na = sum(x * x for x in fa) ** 0.5 + 1e-12
            nb = sum(x * x for x in fb) ** 0.5 + 1e-12
            sim = max(-1.0, min(1.0, dot / (na * nb)))
            try:
                tags = json.loads(info["tags_json"]) if info["tags_json"] else []
            except json.JSONDecodeError:
                tags = []
            candidates.append(
                {
                    "concept_id": info["concept_id"],
                    "type": info["type"],
                    "title": info["title"],
                    "description": info["description"],
                    "body": info["body"],
                    "tags": tags,
                    "timestamp": info["timestamp"],
                    "fts_score": 0.0,
                    "snippet": (info["description"] or info["title"] or "")[:160],
                    "vector_score": sim,
                }
            )
            if len(candidates) >= limit:
                break
        return candidates

    def search(
        self,
        query: str,
        *,
        type_filter: list[str] | None = None,
        tag_filter: list[str] | None = None,
        tenant_id: str | None = None,
        top_k: int = 10,
        query_embedding: list[float] | None = None,
        vector_weight: float = 0.5,
    ) -> list[CatalogHit]:
        """Hybrid retrieval: structured filter + FTS5 + vector with RRF.

        The work is split across five private helpers, one per
        stage of the pipeline:

          1. ``_keyword_candidates``   — FTS5 or structured only
          2. ``_vector_candidates``    — vec0 cosine over eligible rows
          3. ``_merge_candidates``     — union by concept_id
          4. ``_reciprocal_rank_fusion`` — RRF blend with vector_weight
          5. ``_build_hits``           — top-k → CatalogHit conversion

        Args:
            query: Free-text query.
            type_filter: Optional OKF ``type`` values to restrict to.
            tag_filter: Optional required tags (intersection).
            tenant_id: Tenant scope. If ``None``, searches all
                tenants.
            top_k: Maximum hits to return.
            query_embedding: Optional query embedding for vector
                retrieval.
            vector_weight: Weight of vector score in final ranking.

        Returns:
            A list of :class:`CatalogHit` ordered by descending score.
        """
        if not (0.0 <= vector_weight <= 1.0):
            raise ValueError(f"vector_weight must be in [0, 1], got {vector_weight}")
        oversample = max(top_k * 3, 30)

        fts_candidates = self._keyword_candidates(
            query=query,
            oversample=oversample,
            tenant_id=tenant_id,
            type_filter=type_filter,
            tag_filter=tag_filter,
        )
        vec_candidates = self._vector_candidates(
            query_embedding=query_embedding,
            oversample=oversample,
            tenant_id=tenant_id,
            type_filter=type_filter,
            tag_filter=tag_filter,
        )

        all_candidates = self._merge_candidates(fts_candidates, vec_candidates)
        if not all_candidates:
            return []

        scored = self._reciprocal_rank_fusion(all_candidates, vector_weight)
        return self._build_hits(scored, top_k)

    def _keyword_candidates(
        self,
        *,
        query: str,
        oversample: int,
        tenant_id: str | None,
        type_filter: list[str] | None,
        tag_filter: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Stage 1: FTS5 hit list when ``query`` is non-empty, structured only otherwise."""
        if query:
            return self.fetch_fts_candidates(
                query,
                tenant_id=tenant_id,
                type_filter=type_filter,
                tag_filter=tag_filter,
                limit=oversample,
            )
        return self.fetch_structured_candidates(
            tenant_id=tenant_id, type_filter=type_filter, tag_filter=tag_filter, limit=oversample
        )

    def _vector_candidates(
        self,
        *,
        query_embedding: list[float] | None,
        oversample: int,
        tenant_id: str | None,
        type_filter: list[str] | None,
        tag_filter: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Stage 2: vec0 cosine ranking, skipped when the embedding extension is unavailable."""
        if query_embedding is None or self.sqlite_vec is None:
            return []
        return self.fetch_vector_candidates(
            query_embedding,
            tenant_id=tenant_id,
            type_filter=type_filter,
            tag_filter=tag_filter,
            limit=oversample,
        )

    @staticmethod
    def _merge_candidates(
        fts: list[dict[str, Any]], vec: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Stage 3: union by ``concept_id``. FTS wins on collision because it carries snippet + bm25."""
        merged: dict[str, dict[str, Any]] = {}
        for c in fts:
            merged[c["concept_id"]] = c
        for c in vec:
            if c["concept_id"] not in merged:
                merged[c["concept_id"]] = c
        return list(merged.values())

    @staticmethod
    def _reciprocal_rank_fusion(
        candidates: list[dict[str, Any]], vector_weight: float
    ) -> list[dict[str, Any]]:
        """Stage 4: combine FTS and vector ranks via RRF, write back ``score``."""
        fts_ranked = sorted(
            (c for c in candidates if c["fts_score"] != 0.0),
            key=lambda c: c["fts_score"],  # bm25 is negative; lower = better
        )
        vec_ranked = sorted(
            (c for c in candidates if c["vector_score"] != 0.0), key=lambda c: -c["vector_score"]
        )
        rrf: dict[str, float] = {c["concept_id"]: 0.0 for c in candidates}
        for rank, c in enumerate(fts_ranked):
            rrf[c["concept_id"]] += (1.0 - vector_weight) / (RRF_K + rank + 1)
        for rank, c in enumerate(vec_ranked):
            rrf[c["concept_id"]] += vector_weight / (RRF_K + rank + 1)
        if not fts_ranked and not vec_ranked:
            for cid in rrf:
                rrf[cid] = 1.0 / RRF_K
        for c in candidates:
            c["score"] = rrf[c["concept_id"]]
        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates

    @staticmethod
    def _build_hits(candidates: list[dict[str, Any]], top_k: int) -> list[CatalogHit]:
        """Stage 5: top-k slice → CatalogHit conversion."""
        out: list[CatalogHit] = []
        for c in candidates[:top_k]:
            out.append(
                CatalogHit(
                    concept_id=c["concept_id"],
                    type=c["type"],
                    title=c["title"],
                    description=c["description"],
                    score=c["score"],
                    fts_score=c["fts_score"],
                    vector_score=c["vector_score"],
                    tags=c["tags"],
                    timestamp=c["timestamp"],
                    snippet=c["snippet"],
                )
            )
        return out

    def close(self) -> None:
        self.conn.close()


# --- Singleton -----------------------------------------------------------


SINGLETON: OKFCatalog | None = None


def get_catalog() -> OKFCatalog:
    """Return the singleton :class:`OKFCatalog`.

    Reads the catalog DB path from ``INTELLIQX_OKF_DB`` (default
    ``:memory:``) and the vector dim from ``INTELLIQX_OKF_DIM``
    (default ``None`` — no vector re-rank). The OKF bundle path
    is read from ``INTELLIQX_OKF_BUNDLE`` (default unset); when
    set, :func:`load_okf_catalog_from_bundle` is the right way
    to populate it.

    Use :func:`reset_catalog` between tests for isolation.
    """
    global SINGLETON
    if SINGLETON is None:
        import os

        db_path = os.environ.get("INTELLIQX_OKF_DB", ":memory:")
        dim_str = os.environ.get("INTELLIQX_OKF_DIM")
        dim = int(dim_str) if dim_str else None
        SINGLETON = OKFCatalog(db_path=db_path, dim=dim)
    return SINGLETON


def set_catalog(catalog: OKFCatalog) -> None:
    """Replace the singleton catalog (for tests and bootstrap)."""
    global SINGLETON
    SINGLETON = catalog


def reset_catalog() -> None:
    """Clear the singleton catalog (for tests)."""
    import contextlib

    global SINGLETON
    if SINGLETON is not None:
        with contextlib.suppress(Exception):
            SINGLETON.close()
    SINGLETON = None


def load_okf_catalog_from_bundle(
    bundle: OKFBundle, *, catalog: OKFCatalog | None = None, tenant_id: str = "_global"
) -> int:
    """Build (or rebuild) a catalog from a loaded :class:`OKFBundle`.

    Convenience wrapper around :meth:`OKFCatalog.build_catalog`.
    Returns the number of concepts ingested.
    """
    return (catalog or get_catalog()).build_catalog(bundle, tenant_id=tenant_id)
