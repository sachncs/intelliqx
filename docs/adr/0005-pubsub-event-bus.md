# ADR-0005: Pub/Sub event bus semantics across clouds

- **Status**: Accepted
- **Context**: IntelliqX needs a portable event bus that runs identically on AWS (EventBridge + SQS), GCP (Pub/Sub), and Modal (modal.Queue).
- **Decision**: Define an `EventBus` interface with `publish(topic, event)` and `subscribe(topic, handler, *, dlq)`. Cloud-specific adapters translate to native primitives. DLQ + retry policies enforced by the bus, not by individual agents.
- **Consequences**:
  - Pros: agents stay cloud-agnostic; replay/DLQ semantics consistent.
  - Cons: cloud-specific features (e.g., EventBridge archive) require explicit adapter support.

## References
- Phase 1 / 2 plans