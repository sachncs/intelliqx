# ADR-0004: Knowledge Graph as Parquet + DuckDB

- **Status**: Accepted
- **Context**: AQIP does not need real-time graph traversals; batch and RAG-style retrieval suffice.
- **Decision**: Store nodes and edges as Parquet partitions in object storage. Query via DuckDB in-process (columnar, predicate pushdown).
- **Consequences**:
  - Pros: zero managed DB cost, serverless-friendly (runs anywhere Python runs), scales to millions of edges.
  - Cons: not a true OLTP graph; concurrent writes need an append-only log + compaction step.

## References
- Phase 0 plan: § 0.3