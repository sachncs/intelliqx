# ADR-0007: Single agent framework (AgentBase + decorators)

- **Status**: Accepted
- **Context**: 30+ agents across 4 tiers must share observability, retry, validation, and event emission.
- **Decision**: Define `AgentBase[InputT, OutputT]` with a single `run(ctx, input)` method, plus decorators (`@traced_agent`) and a global registry. The compute runtime calls `agent.invoke(request)` which routes via `INPUT_MODEL`/`OUTPUT_MODEL`.
- **Consequences**:
  - Pros: uniform metrics, traces, retries; one mental model; tested once.
  - Cons: any cross-cutting change touches the base class.

## References
- Phase 0 plan: `libs/aqip-agents/`