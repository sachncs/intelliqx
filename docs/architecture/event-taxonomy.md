# IntelliqX Event Taxonomy

This document describes the event topics the Coordination agents publish
and consume. Every event is an instance of a class defined in
`agents/coordination/events.py` and carries an
:class:`intelliqx_core.events.EventMetadata` envelope.

## Event topics

| Topic | Class | Producer | Trigger |
|---|---|---|---|
| `run.started` | `RunStarted` | Orchestrator | A workflow run begins. |
| `run.completed` | `RunCompleted` | Orchestrator | A workflow run terminates (any `RunStatus`). |
| `plan.node.started` | `PlanNodeStarted` | Orchestrator | A plan node's agent invocation begins. |
| `plan.node.completed` | `PlanNodeCompleted` | Orchestrator | A plan node's agent invocation ends. |
| `plan.generated` | `PlanGenerated` | Planner (future) | A plan is produced. |

The agent-invocation events (`AgentInvocationStarted` /
`AgentInvocationCompleted`) are emitted by the compute runtime's
hooks when those are configured.

## Topic convention

Topics use a dotted ``"<noun>.<verb>(.<modifier>)"`` pattern with the
verb last. This makes wildcards natural — ``"plan.node.*"`` would
match both started and completed events for plan nodes — and aligns
with how the in-process event bus treats topics.

## Envelope

Every event is wrapped in an :class:`intelliqx_core.events.EventEnvelope`
for the wire format. The envelope's ``metadata`` field is what
audit, tracing, and governance consume; the rest of the envelope
is opaque to those subsystems.

```
EventEnvelope {
  detail_type: "RunCompleted"
  metadata: EventMetadata {
    event_id, tenant_id, correlation_id?, causation_id?, produced_by, schema_version, emitted_at
  }
  payload: { ... event-specific fields ... }
}
```

## Correlation

The ``metadata.correlation_id`` field is the join key for
cross-event analysis. The Orchestrator sets it to the run id at
the start of every run, and downstream consumers (Reporting,
Learning) can group events by ``correlation_id`` to reconstruct
the timeline of a run.

## Schema versioning

``metadata.schema_version`` defaults to ``"1.0"``. Bump it on any
breaking change to the payload shape; consumers should check the
version and handle older payloads gracefully.

## Producer ownership

| Class | Module | META |
|---|---|---|
| `PlanGenerated` | `agents.coordination.events` | Orchestrator or Planner |
| `PlanNodeStarted` / `PlanNodeCompleted` | `agents.coordination.events` | Orchestrator |
| `RunStarted` / `RunCompleted` | `agents.coordination.events` | Orchestrator |
| `AgentInvocationStarted` / `AgentInvocationCompleted` | `agents.coordination.events` | Compute runtime hooks |

## Persistence vs. transient

All events are *transient*: they are published to the event bus
and may be persisted by subscribers (the Reporting agent persists
summaries; the Learning agent persists outcomes). No event
storage lives inside the platform itself.
