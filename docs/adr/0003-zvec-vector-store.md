# ADR-0003: zvec as the embedded vector store

- **Status**: Accepted
- **Context**: A managed vector DB adds cluster ops, cold-start latency, and recurring cost. IntelliqX agents are short-lived and need sub-100ms vector search.
- **Decision**: Use Zilliz zvec (in-process C++/Rust core with Python bindings). Indices persisted to IntelliqX object store; loaded into agent process on cold start.
- **Consequences**:
  - Pros: zero cluster ops, no warmup, portable (one binary).
  - Cons: index size limited by agent memory; tenant-sharded indices required for >1M vectors.

## References
- Phase 0 plan: § 0.3 / Phase 7 plan