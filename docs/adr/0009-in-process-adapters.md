# ADR-0009: Local testing via in-process adapters

- **Status**: Accepted
- **Context**: IntelliqX must run end-to-end locally without external infrastructure or vendor credentials.
- **Decision**: Every `intelliqx-*` lib ships an in-process or filesystem-backed implementation (`InMemoryEventBus`, `InMemoryObjectStore`, `LocalFileSystemObjectStore`, `InMemoryStateStore`, `InMemoryVectorIndex`, `InProcessComputeRuntime`, `FakeLLMClient`). CI runs the full test matrix against these. Docker Compose is provided for production-like local infra but is optional.
- **Consequences**:
  - Pros: fast feedback, no infra deps in CI, identical code paths.
  - Cons: subtle behavior differences vs. real cloud; contract tests reduce risk.

## References
- Phase 0 plan: § 0.4