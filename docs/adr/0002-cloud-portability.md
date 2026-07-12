# ADR-0002: Cloud portability via adapter libraries

- **Status**: Accepted
- **Context**: AQIP must run on AWS, GCP, and Modal without rewriting agents per cloud.
- **Decision**: All cloud-specific access goes through `aqip-*` libs (`aqip-events`, `aqip-storage`, `aqip-state`, `aqip-vector`, `aqip-llm`, `aqip-compute`). Each lib exposes one interface with cloud-specific implementations selected at deploy time via `AQIP_CLOUD`.
- **Consequences**:
  - Pros: One agent codebase across three clouds. New clouds = new adapter only.
  - Cons: Adapter implementations must keep semantics identical (covered by contract tests).

## References
- Phase 2 plan: `docs/phases/phase-2-multicloud.md`