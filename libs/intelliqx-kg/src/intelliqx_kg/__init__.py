"""Knowledge Graph: file-based (Parquet + DuckDB) for AQIP.

The platform's knowledge graph is **file-based by design**. Nodes and
edges are serialised as Parquet partitions in the AQIP object store;
DuckDB reads them in-process for sub-second analytics. We avoid a
managed graph database for three reasons:

1. **No managed DB to operate.** Cold-start is one object-store
   ``get`` plus a DuckDB ``read_parquet``; no cluster, no replicas.
2. **Serverless-friendly.** Every operation is a single async method
   that finishes in the same Lambda / Cloud Function / Modal Function
   invocation.
3. **Partition pruning.** Filtering on ``tenant_id`` happens at the
   DuckDB scan, so tenants never see each other's data.

The trade-off is no OLTP graph traversal; for AQIP's usage (RAG
retrieval, lineage, requirements traceability) batch analytics
dominate anyway.
"""

from intelliqx_kg.graph import Edge, KGQueryResult, KnowledgeGraph, Node, get_kg

__all__ = ["Edge", "KGQueryResult", "KnowledgeGraph", "Node", "get_kg"]
