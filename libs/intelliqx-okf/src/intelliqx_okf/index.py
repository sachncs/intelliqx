"""Single-file OKF index backed by SQLite + sqlite-vec.

The index is the only writer and the only reader; one DB file holds
one schema (concepts + FTS5 mirror + vec0 column + one metadata row
recording the active embedder). Three public methods:

* :meth:`Index.write` — upsert one :class:`~intelliqx_okf.concept.OKFConcept`.
* :meth:`Index.read` — keyword + optional vector hybrid search.
* :meth:`Index.close` — release the connection.

Build-side callers convert concepts to embeddings once via an
:data:`Embedder`. Read-side callers either reuse the existing index or
pass a query embedding; without one, the read degrades to FTS5 only.
"""

from __future__ import annotations

import json
import sqlite3
import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING

from intelliqx_okf.concept import OKFConcept
from intelliqx_okf.embed import Embedder, EmbeddingMismatchError

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class Hit:
    """One read result. ``score`` is a float in ``[0, 1]`` (higher is better)."""

    concept: OKFConcept
    score: float


class Index:
    """SQLite + FTS5 + sqlite-vec index over OKF concepts."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS concepts (
        concept_id TEXT PRIMARY KEY,
        rowid      INTEGER NOT NULL,
        type       TEXT NOT NULL,
        title      TEXT,
        description TEXT,
        body       TEXT NOT NULL,
        tags_json  TEXT NOT NULL DEFAULT '[]',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        timestamp  TEXT
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS concepts_fts USING fts5(
        concept_id UNINDEXED,
        title,
        description,
        body,
        content='concepts',
        content_rowid='rowid',
        tokenize='porter unicode61'
    );
    CREATE TRIGGER IF NOT EXISTS concepts_ai AFTER INSERT ON concepts BEGIN
        INSERT INTO concepts_fts(rowid, concept_id, title, description, body)
        VALUES (new.rowid, new.concept_id, new.title, new.description, new.body);
    END;
    CREATE TRIGGER IF NOT EXISTS concepts_ad AFTER DELETE ON concepts BEGIN
        INSERT INTO concepts_fts(concepts_fts, rowid, concept_id, title, description, body)
        VALUES ('delete', old.rowid, old.concept_id, old.title, old.description, old.body);
    END;
    CREATE TRIGGER IF NOT EXISTS concepts_au AFTER UPDATE ON concepts BEGIN
        INSERT INTO concepts_fts(concepts_fts, rowid, concept_id, title, description, body)
        VALUES ('delete', old.rowid, old.concept_id, old.title, old.description, old.body);
        INSERT INTO concepts_fts(rowid, concept_id, title, description, body)
        VALUES (new.rowid, new.concept_id, new.title, new.description, new.body);
    END;
    CREATE TABLE IF NOT EXISTS index_meta (
        embedder_name TEXT PRIMARY KEY,
        embedder_dim  INTEGER NOT NULL
    );
    """

    def __init__(self, path: str | sqlite3.Connection, *, embed: Embedder) -> None:
        self.embed = embed
        if isinstance(path, sqlite3.Connection):
            self._conn = path
            self._owns = False
        else:
            self._conn = sqlite3.connect(path)
            self._owns = True
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(self.SCHEMA)
        self._load_extension()
        self._init_vector_column()
        self._verify_or_init_meta()

    def _load_extension(self) -> None:
        try:
            import sqlite_vec  # type: ignore[import-untyped]
        except ImportError as err:
            raise RuntimeError("sqlite-vec is required for the OKF index") from err
        ext = sqlite_vec.loadable_path()
        self._conn.enable_load_extension(True)
        try:
            for candidate in (ext, ext + ".dylib", ext + ".so"):
                try:
                    self._conn.load_extension(candidate)
                    return
                except sqlite3.OperationalError:
                    continue
        finally:
            self._conn.enable_load_extension(False)
        raise RuntimeError("sqlite-vec shared library not found")

    def _init_vector_column(self) -> None:
        cur = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='concepts_vec'"
        )
        if cur.fetchone() is None:
            self._conn.execute(
                f"CREATE VIRTUAL TABLE concepts_vec USING vec0(embedding float[{self.embed.dim}] distance_metric=cosine)"
            )
            self._conn.commit()

    def _verify_or_init_meta(self) -> None:
        cur = self._conn.execute("SELECT embedder_name, embedder_dim FROM index_meta LIMIT 1")
        row = cur.fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO index_meta(embedder_name, embedder_dim) VALUES (?, ?)",
                (self.embed.name, self.embed.dim),
            )
            self._conn.commit()
            return
        existing_name, existing_dim = row["embedder_name"], int(row["embedder_dim"])
        if existing_name != self.embed.name or existing_dim != self.embed.dim:
            raise EmbeddingMismatchError(
                existing_name=existing_name,
                existing_dim=existing_dim,
                requested_name=self.embed.name,
                requested_dim=self.embed.dim,
            )

    @staticmethod
    def _pack(vec: Sequence[float]) -> bytes:
        return struct.pack(f"<{len(vec)}f", *vec)

    def write(self, concept: OKFConcept) -> None:
        """Upsert one concept and (if its body is non-empty) its embedding."""
        tags_json = json.dumps(concept.frontmatter.tags or [])
        metadata_json = json.dumps(concept.frontmatter.extra_fields or {})
        timestamp = (
            concept.frontmatter.timestamp.isoformat() if concept.frontmatter.timestamp else None
        )
        text_parts = [
            concept.frontmatter.title or "",
            concept.frontmatter.description or "",
            concept.body or "",
        ]
        text = " ".join(part for part in text_parts if part).strip()
        vec: list[float] | None = self.embed.embed(text) if text else None
        if vec is not None and len(vec) != self.embed.dim:
            raise ValueError(f"Embedding dim mismatch: expected {self.embed.dim}, got {len(vec)}")
        next_id = self._conn.execute("SELECT COALESCE(MAX(rowid), 0) + 1 FROM concepts").fetchone()[
            0
        ]
        with self._conn:
            cur = self._conn.execute(
                """INSERT OR REPLACE INTO concepts(
                       concept_id, rowid, type, title, description, body, tags_json, metadata_json, timestamp
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    concept.concept_id,
                    next_id,
                    concept.frontmatter.type,
                    concept.frontmatter.title,
                    concept.frontmatter.description,
                    concept.body,
                    tags_json,
                    metadata_json,
                    timestamp,
                ),
            )
            rowid = cur.lastrowid
            self._conn.execute("DELETE FROM concepts_vec WHERE rowid = ?", (rowid,))
            if vec is not None:
                self._conn.execute(
                    "INSERT INTO concepts_vec(rowid, embedding) VALUES (?, ?)",
                    (rowid, self._pack(vec)),
                )

    def _fts_candidates(
        self, query: str, *, type_filter: str | None, tag_filter: str | None, limit: int
    ) -> list[tuple[int, float]]:
        sql = [
            "SELECT rowid, bm25(concepts_fts) AS score FROM concepts_fts WHERE concepts_fts MATCH ?"
        ]
        params: list[object] = [self._quote_fts(query)]
        if type_filter is not None:
            sql.append("AND rowid IN (SELECT rowid FROM concepts WHERE type = ?)")
            params.append(type_filter)
        if tag_filter is not None:
            sql.append(
                "AND rowid IN (SELECT rowid FROM concepts WHERE EXISTS ("
                "SELECT 1 FROM json_each(tags_json) WHERE value = ?))"
            )
            params.append(tag_filter)
        sql.append("ORDER BY score ASC LIMIT ?")
        params.append(limit)
        rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [(int(r["rowid"]), float(r["score"])) for r in rows]

    def _vector_candidates(
        self,
        query_embedding: Sequence[float],
        *,
        type_filter: str | None,
        tag_filter: str | None,
        limit: int,
    ) -> list[tuple[int, float]]:
        if len(query_embedding) != self.embed.dim:
            raise ValueError(
                f"Embedding dim mismatch: expected {self.embed.dim}, got {len(query_embedding)}"
            )
        sql = [
            "SELECT v.rowid AS rowid, v.distance AS distance",
            "FROM concepts_vec v",
            "JOIN concepts c ON c.rowid = v.rowid",
            "WHERE v.embedding MATCH ? AND k = ?",
        ]
        params: list[object] = [self._pack(query_embedding), int(limit)]
        if type_filter is not None:
            sql.append("AND c.type = ?")
            params.append(type_filter)
        if tag_filter is not None:
            sql.append("AND EXISTS (SELECT 1 FROM json_each(c.tags_json) WHERE value = ?)")
            params.append(tag_filter)
        rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [
            (int(r["rowid"]), float(r["distance"] or 0.0))
            for r in rows
            if r["distance"] is not None
        ]

    def _hybrid(
        self,
        *,
        query: str,
        query_embedding: Sequence[float] | None,
        top: int,
        type_filter: str | None,
        tag_filter: str | None,
        vector_weight: float,
    ) -> list[Hit]:
        k = 60
        rrf: dict[int, float] = {}
        seen_rank: dict[int, int] = {}
        if query:
            fts_rows = self._fts_candidates(
                query, type_filter=type_filter, tag_filter=tag_filter, limit=max(top * 4, 30)
            )
            for rank, (rowid, _bm25) in enumerate(fts_rows):
                rrf[rowid] = rrf.get(rowid, 0.0) + (1.0 - vector_weight) / (k + rank + 1)
                seen_rank.setdefault(rowid, rank)
        if query_embedding is not None:
            vec_rows = self._vector_candidates(
                query_embedding,
                type_filter=type_filter,
                tag_filter=tag_filter,
                limit=max(top * 4, 30),
            )
            for rank, (rowid, distance) in enumerate(vec_rows):
                score = max(0.0, min(1.0, 1.0 - distance))
                rrf[rowid] = rrf.get(rowid, 0.0) + vector_weight * score / (k + rank + 1)
                seen_rank.setdefault(rowid, rank)
        if not rrf:
            return []
        top_ids = sorted(rrf.items(), key=lambda item: item[1], reverse=True)[:top]
        rows = self._conn.execute(
            f"SELECT rowid, concept_id, type, title, description, body, tags_json, metadata_json, timestamp FROM concepts WHERE rowid IN ({','.join('?' for _ in top_ids)})",
            [rowid for rowid, _ in top_ids],
        ).fetchall()
        by_rowid = {int(r["rowid"]): r for r in rows}
        hits: list[Hit] = []
        max_rrf = max(rrf.values()) or 1.0
        for rowid, score in top_ids:
            row = by_rowid.get(rowid)
            if row is None:
                continue
            concept = OKFConcept.model_validate(_row_to_concept_payload(row))
            hits.append(Hit(concept=concept, score=score / max_rrf))
        return hits

    def read(
        self,
        query: str,
        *,
        top: int = 10,
        type: str | None = None,
        tag: str | None = None,
        query_embedding: Sequence[float] | None = None,
        vector_weight: float = 0.5,
    ) -> list[Hit]:
        if top < 1:
            raise ValueError(f"top must be >= 1, got {top}")
        if not (0.0 <= vector_weight <= 1.0):
            raise ValueError(f"vector_weight must be in [0, 1], got {vector_weight}")
        return self._hybrid(
            query=query,
            query_embedding=query_embedding,
            top=top,
            type_filter=type,
            tag_filter=tag,
            vector_weight=vector_weight,
        )

    @staticmethod
    def _quote_fts(query: str) -> str:
        tokens = [tok for tok in query.split() if tok]
        if not tokens:
            return '""'
        return " ".join(f'"{tok.replace(chr(34), "")}"' for tok in tokens)

    def close(self) -> None:
        if self._owns:
            self._conn.close()


def _row_to_concept_payload(row: sqlite3.Row) -> dict:
    from intelliqx_okf.frontmatter import OKFFrontmatter

    extras = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
    frontmatter = OKFFrontmatter.model_validate(
        {
            "type": row["type"],
            "title": row["title"],
            "description": row["description"],
            "tags": json.loads(row["tags_json"]) if row["tags_json"] else [],
            "timestamp": row["timestamp"],
            **extras,
        }
    )
    return {"concept_id": row["concept_id"], "frontmatter": frontmatter, "body": row["body"]}


def open_index(path: str = ":memory:", *, embed: Embedder | None = None) -> Index:
    """Open the default :class:`Index` for the application.

    ``embed`` defaults to the Pydaxis-AI-backed
    :data:`Embedder` returned by :func:`intelliqx_ai.runtime.build_embedder`.
    Path defaults to the in-memory database; production uses
    ``$INTELLIQX_OKF_DB`` or a deployment-supplied file.
    """
    from intelliqx_okf.llm_embed import PydaxisAIEmbedder

    resolved = embed if embed is not None else PydaxisAIEmbedder.from_default()
    return Index(path, embed=resolved)


__all__ = ["Hit", "Index", "open_index"]
