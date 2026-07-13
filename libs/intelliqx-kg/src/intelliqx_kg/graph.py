"""Knowledge graph implementation backed by Parquet + DuckDB.

The :class:`KnowledgeGraph` keeps an in-memory mirror of every node
and edge for fast query access. Writes are batched into Parquet
partitions and flushed to the IntelliqX object store; reads register the
in-memory tables as DuckDB views and execute SQL against them.

Storage layout in the object store::

    <collection>/nodes/part-<NNNNNNNN>.parquet
    <collection>/edges/part-<NNNNNNNN>.parquet

The numeric suffix is the row count at flush time; it is monotonic
per-collection so callers can list partitions lexicographically.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterable
from typing import Any

import duckdb
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from intelliqx_storage.store import ObjectStore, get_object_store
from pydantic import BaseModel, ConfigDict, Field


class Node(BaseModel):
    """A knowledge graph node.

    Attributes:
        id: Unique id (typically a ULID or a derived selector).
        type: Node type (e.g. ``"Requirement"``, ``"File"``,
            ``"UIElement"``). Free-form string; downstream code is
            responsible for type-specific behaviour.
        tenant_id: Owning tenant. Used to scope queries.
        attrs: Free-form attribute dict. Serialised as a JSON string
            in Parquet to keep the schema flat.
        embedding_ref: Optional pointer into the vector index
            (``{collection}/{id}``). Lets the RAG agent join KG and
            vector data without re-embedding.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    tenant_id: str
    attrs: dict[str, Any] = Field(default_factory=dict)
    embedding_ref: str | None = None


class Edge(BaseModel):
    """A knowledge graph edge.

    Attributes:
        src: Source node id.
        dst: Destination node id.
        type: Edge type (e.g. ``"IMPORTS"``, ``"VALIDATES"``,
            ``"RELATED_TO"``). Free-form string.
        tenant_id: Owning tenant. Must match the source and
            destination nodes' ``tenant_id`` (caller responsibility).
        weight: Numeric weight. Defaults to 1.0; the RAG agent uses
            it for ranking, not for filtering.
        attrs: Free-form attribute dict (e.g. ``{"shared_keywords": [...]}``).
    """

    model_config = ConfigDict(extra="forbid")

    src: str
    dst: str
    type: str
    tenant_id: str
    weight: float = 1.0
    attrs: dict[str, Any] = Field(default_factory=dict)


class KGQueryResult(BaseModel):
    """The result of a DuckDB query.

    Attributes:
        rows: Each row as a dict keyed by column name.
        columns: The column names in declaration order.
        row_count: Convenience for ``len(rows)``.
    """

    model_config = ConfigDict(extra="forbid")

    rows: list[dict[str, Any]]
    columns: list[str]
    row_count: int


class KnowledgeGraph:
    """Knowledge graph with Parquet persistence + DuckDB query engine.

    The class maintains a dual representation: an in-memory list of
    nodes/edges for fast access, and Parquet partitions in the
    object store for persistence. Queries register the in-memory
    tables as DuckDB views and execute SQL against them.

    Args:
        collection: Top-level namespace (e.g. ``"default"``,
            ``"tenant_acme"``). Each collection has its own object
            store sub-prefix.
        storage: Object store to use. Defaults to the singleton.
        con: Optional pre-existing DuckDB connection. Used by tests
            that want a shared in-memory DB across instances.
    """

    def __init__(
        self,
        *,
        collection: str = "default",
        storage: ObjectStore | None = None,
        con: duckdb.DuckDBPyConnection | None = None,
    ) -> None:
        self.collection = collection
        self.__storage = storage or get_object_store()
        # In-memory DuckDB instance per KnowledgeGraph. Cheap; one
        # per process is the typical setup.
        self.__con = con or duckdb.connect(":memory:")
        # Buffers used to build the next Parquet partition.
        self.__nodes_arrow: list[dict[str, Any]] = []
        self.__edges_arrow: list[dict[str, Any]] = []
        # In-memory snapshot for fast query in tests.
        self.__nodes_table: list[Node] = []
        self.__edges_table: list[Edge] = []

    async def add_nodes(self, nodes: Iterable[Node]) -> int:
        """Add ``nodes`` to the graph.

        Nodes are appended to the in-memory list immediately and
        their serialised form is buffered for the next Parquet
        flush. The flush happens once at the end of the call to
        amortise I/O.
        """
        added = 0
        for n in nodes:
            self.__nodes_table.append(n)
            self.__nodes_arrow.append(
                {
                    "id": n.id,
                    "type": n.type,
                    "tenant_id": n.tenant_id,
                    "attrs": json.dumps(n.attrs),
                    "embedding_ref": n.embedding_ref,
                }
            )
            added += 1
        if added:
            await self._flush("nodes")
        return added

    async def add_edges(self, edges: Iterable[Edge]) -> int:
        """Add ``edges`` to the graph.

        Same buffering / flushing strategy as :meth:`add_nodes`.
        """
        added = 0
        for e in edges:
            self.__edges_table.append(e)
            self.__edges_arrow.append(
                {
                    "src": e.src,
                    "dst": e.dst,
                    "type": e.type,
                    "tenant_id": e.tenant_id,
                    "weight": e.weight,
                    "attrs": json.dumps(e.attrs),
                }
            )
            added += 1
        if added:
            await self._flush("edges")
        return added

    async def _flush(self, kind: str) -> None:
        """Write the buffered ``kind`` rows to a new Parquet partition.

        Snappy compression is used because it gives a 3-5x ratio on
        our typical JSON-payload schemas with negligible CPU cost.
        """
        rows = self.__nodes_arrow if kind == "nodes" else self.__edges_arrow
        if not rows:
            return
        if kind == "nodes":
            schema = pa.schema(
                [
                    ("id", pa.string()),
                    ("type", pa.string()),
                    ("tenant_id", pa.string()),
                    ("attrs", pa.string()),
                    ("embedding_ref", pa.string()),
                ]
            )
        else:
            schema = pa.schema(
                [
                    ("src", pa.string()),
                    ("dst", pa.string()),
                    ("type", pa.string()),
                    ("tenant_id", pa.string()),
                    ("weight", pa.float64()),
                    ("attrs", pa.string()),
                ]
            )
        table = pa.Table.from_pylist(rows, schema=schema)
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="snappy")
        # The key embeds the current node-table size so successive
        # partitions get strictly increasing numbers.
        key = f"{self.collection}/{kind}/part-{len(self.__nodes_table):08d}.parquet"
        await self.__storage.put(key, buf.getvalue(), content_type="application/octet-stream")
        rows.clear()

    def register_views(self) -> None:
        """Register the in-memory tables as DuckDB views.

        ``kg_nodes`` and ``kg_edges`` are the standard view names used
        by :meth:`query` and :meth:`neighbors`. The empty case
        creates a one-row ``WHERE FALSE`` view so that ``SELECT *
        FROM kg_nodes`` is well-typed even when the graph is empty.
        """
        self.__con.execute("DROP VIEW IF EXISTS kg_nodes")
        self.__con.execute("DROP VIEW IF EXISTS kg_edges")
        if self.__nodes_table:
            nodes_data = [
                {
                    "id": n.id,
                    "type": n.type,
                    "tenant_id": n.tenant_id,
                    "attrs": json.dumps(n.attrs),
                    "embedding_ref": n.embedding_ref,
                }
                for n in self.__nodes_table
            ]
            nodes_tbl = pa.Table.from_pylist(nodes_data)
            self.__con.register("kg_nodes_df", nodes_tbl)
            self.__con.execute("CREATE VIEW kg_nodes AS SELECT * FROM kg_nodes_df")
        else:
            # Typed-but-empty view: ``SELECT * FROM kg_nodes`` returns
            # zero rows but with the expected column types.
            self.__con.execute(
                "CREATE VIEW kg_nodes AS SELECT NULL::VARCHAR AS id, NULL::VARCHAR AS type,"
                " NULL::VARCHAR AS tenant_id, NULL::VARCHAR AS attrs,"
                " NULL::VARCHAR AS embedding_ref WHERE FALSE"
            )
        if self.__edges_table:
            edges_data = [
                {
                    "src": e.src,
                    "dst": e.dst,
                    "type": e.type,
                    "tenant_id": e.tenant_id,
                    "weight": e.weight,
                    "attrs": json.dumps(e.attrs),
                }
                for e in self.__edges_table
            ]
            edges_tbl = pa.Table.from_pylist(edges_data)
            self.__con.register("kg_edges_df", edges_tbl)
            self.__con.execute("CREATE VIEW kg_edges AS SELECT * FROM kg_edges_df")
        else:
            self.__con.execute(
                "CREATE VIEW kg_edges AS SELECT NULL::VARCHAR AS src, NULL::VARCHAR AS dst,"
                " NULL::VARCHAR AS type, NULL::VARCHAR AS tenant_id, NULL::DOUBLE AS weight,"
                " NULL::VARCHAR AS attrs WHERE FALSE"
            )

    def query(self, sql: str, *, params: list[Any] | None = None) -> KGQueryResult:
        """Execute a SQL query against the graph.

        Conventions:
            * Views: ``kg_nodes``, ``kg_edges``.
            * ``kg_nodes`` columns: ``id``, ``type``, ``tenant_id``,
              ``attrs`` (JSON string), ``embedding_ref``.
            * ``kg_edges`` columns: ``src``, ``dst``, ``type``,
              ``tenant_id``, ``weight``, ``attrs`` (JSON string).

        Args:
            sql: Any DuckDB-compatible SELECT.
            params: Positional parameters (``?`` placeholders).

        Returns:
            A :class:`KGQueryResult` with rows, columns, and
            row_count populated.
        """
        self.register_views()
        result = self.__con.execute(sql, params or []).fetchall()
        # ``description`` is None for queries with no rows; guard
        # against that.
        cols = [d[0] for d in self.__con.description] if self.__con.description else []
        rows = [dict(zip(cols, r)) for r in result]
        return KGQueryResult(rows=rows, columns=cols, row_count=len(rows))

    def neighbors(
        self,
        node_id: str,
        *,
        tenant_id: str | None = None,
        edge_type: str | None = None,
        direction: str = "out",
        depth: int = 1,  # noqa: VU001 — reserved for future multi-hop traversal
    ) -> KGQueryResult:
        """Return the neighbour nodes of ``node_id``.

        Direction:
            * ``"out"`` — edges where ``src = node_id``; the result is
              the ``dst`` endpoint.
            * ``"in"``  — edges where ``dst = node_id``; the result is
              the ``src`` endpoint.
            * ``"both"`` — edges touching ``node_id``; the result is
              the other endpoint. Implemented as ``UNION`` of the
              two single-direction queries.

        Tenant and edge-type filters apply to the edges table (not
        the nodes). ``depth`` is currently reserved; the
        implementation always performs a one-hop traversal.
        """
        self.register_views()
        cond: list[str] = []
        params: list[Any] = []
        if tenant_id is not None:
            cond.append("e.tenant_id = ?")
            params.append(tenant_id)
        if edge_type is not None:
            cond.append("e.type = ?")
            params.append(edge_type)
        cond_sql = (" AND ".join(cond)) if cond else "1=1"

        if direction == "out":
            sql = (
                "SELECT DISTINCT n.id, n.type, n.tenant_id, n.attrs "
                "FROM kg_edges e JOIN kg_nodes n ON e.dst = n.id "
                "WHERE e.src = ? AND " + cond_sql + " LIMIT 1000"
            )
            params = [node_id] + params
        elif direction == "in":
            sql = (
                "SELECT DISTINCT n.id, n.type, n.tenant_id, n.attrs "
                "FROM kg_edges e JOIN kg_nodes n ON e.src = n.id "
                "WHERE e.dst = ? AND " + cond_sql + " LIMIT 1000"
            )
            params = [node_id] + params
        else:
            # "both": UNION of the two one-direction queries. The
            # parameter list is duplicated to match the two SELECT
            # statements.
            sql_out = (
                "SELECT DISTINCT n.id, n.type, n.tenant_id, n.attrs "
                "FROM kg_edges e JOIN kg_nodes n ON e.dst = n.id "
                "WHERE e.src = ? AND " + cond_sql + " LIMIT 1000"
            )
            sql_in = (
                "SELECT DISTINCT n.id, n.type, n.tenant_id, n.attrs "
                "FROM kg_edges e JOIN kg_nodes n ON e.src = n.id "
                "WHERE e.dst = ? AND " + cond_sql + " LIMIT 1000"
            )
            full_params = [node_id] + params
            sql = sql_out + " UNION " + sql_in
            params = full_params + full_params

        return self.query(sql, params=params)

    def node_count(self, tenant_id: str | None = None) -> int:
        """Return the number of nodes in the in-memory table.

        Counts are taken from the in-memory mirror, not the
        partitions on disk — so the value reflects only what this
        process has added.
        """
        if tenant_id is None:
            return len(self.__nodes_table)
        return sum(1 for n in self.__nodes_table if n.tenant_id == tenant_id)

    def edge_count(self, tenant_id: str | None = None) -> int:
        """Return the number of edges in the in-memory table."""
        if tenant_id is None:
            return len(self.__edges_table)
        return sum(1 for e in self.__edges_table if e.tenant_id == tenant_id)

    def reset(self) -> None:
        """Drop every node and edge from the in-memory mirror.

        Tests use this for isolation; production should not.
        """
        self.__nodes_table.clear()
        self.__edges_table.clear()
        self.__nodes_arrow.clear()
        self.__edges_arrow.clear()


_SINGLETON: KnowledgeGraph | None = None


def get_kg() -> KnowledgeGraph:
    """Return the singleton :class:`KnowledgeGraph`.

    Use :func:`reset_kg` between tests for isolation.
    """
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = KnowledgeGraph()
    return _SINGLETON


def reset_kg() -> None:
    """Clear the singleton knowledge graph (for tests)."""
    global _SINGLETON
    if _SINGLETON is not None:
        _SINGLETON.reset()
    _SINGLETON = None
