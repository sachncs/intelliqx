# ADR-0005: In-process event bus with Pub/Sub semantics

- **Status**: Accepted
- **Context**: IntelliqX needs a portable event bus that agents interact with regardless of execution environment.
- **Decision**: Define an `EventBus` interface with `publish(topic, event)` and `subscribe(topic, handler, *, dlq)`. The in-memory implementation fans events out to subscribers inside one process; DLQ retry semantics are enforced by the bus, not by individual agents.
- **Consequences**:
  - Pros: agent call sites remain identical across environments; the in-process implementation enables full test isolation.
  - Cons: cross-process fan-out is not currently supported; introducing a broker later would require extending the interface.

## References
- Phase 1 plan
