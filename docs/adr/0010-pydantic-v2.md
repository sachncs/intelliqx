# ADR-0010: Pydantic v2 as the single source of truth for schemas

- **Status**: Accepted
- **Context**: IntelliqX events, agent I/O, and configs all need validation, JSON serialization, and OpenAPI generation.
- **Decision**: Use Pydantic v2 throughout. Event envelopes, goal models, plan nodes, manifests all inherit `BaseModel` with `extra="forbid"` for strict input validation. JSON Schemas generated via Pydantic are stored under `schemas/events/`.
- **Consequences**:
  - Pros: uniform validation, automatic OpenAPI, free `model_dump_json`.
  - Cons: large models slow import; mitigated by lazy imports.

## References
- Phase 0 / 3 / 5 plans