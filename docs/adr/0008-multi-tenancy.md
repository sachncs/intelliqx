# ADR-0008: Multi-tenancy via namespace isolation

- **Status**: Accepted
- **Context**: IntelliqX v3 must serve many tenants from a single deployment with strong isolation.
- **Decision**: Every resource (S3 key, zvec index, KG partition, Redis key, queue) is prefixed by `tenant_id`. Cross-tenant access blocked by `IsolationEnforcer`. Property tests (100 random cross-tenant attempts) verify zero leakage in CI.
- **Consequences**:
  - Pros: cheap, scales linearly, applies to all storage.
  - Cons: requires every new resource to use the prefix; reviewable via linter.

## References
- Phase 7 plan: § 7.4