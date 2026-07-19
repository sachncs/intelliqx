"""Knowledge Graph: file-based (Parquet + DuckDB) for IntelliqX.

The platform's knowledge graph is **file-based by design**. Nodes and
edges are serialised as Parquet partitions in the IntelliqX object store;
DuckDB reads them in-process for sub-second analytics. We avoid a
managed graph database for three reasons:

1. **No managed DB to operate.** Cold-start is one object-store
   ``get`` plus a DuckDB ``read_parquet``; no cluster, no replicas.
2. **Single-shot operations.** Every operation is a single async
   method that finishes in one invocation without external
   coordination.
3. **Partition pruning.** Filtering on ``tenant_id`` happens at the
   DuckDB scan, so tenants never see each other's data.

The trade-off is no OLTP graph traversal; for IntelliqX's usage (RAG
retrieval, lineage, requirements traceability) batch analytics
dominate anyway.
"""

from intelliqx_kg.graph import Edge, KGQueryResult, KnowledgeGraph, Node, get_kg

__all__ = ["Edge", "KGQueryResult", "KnowledgeGraph", "Node", "get_kg"]
