# IntelliqX — Master Implementation Plan

## Overview

This directory contains the per-phase implementation plans for the Autonomous QA Intelligence Platform (IntelliqX).

## Phase Index

| Phase | Scope | Status |
|---|---|---|
| [Phase 0](phase-0-foundations.md) | Foundations — monorepo, libs, infra, CI | COMPLETE |
| [Phase 1](phase-1-coordination.md) | Coordination layer on AWS | COMPLETE |
| [Phase 2](phase-2-multicloud.md) | Coordination multi-cloud parity (GCP + Modal) | COMPLETE |
| [Phase 3](phase-3-intelligence-core.md) | Intelligence domain core | COMPLETE |
| [Phase 4](phase-4-execution.md) | Execution core | COMPLETE |
| [Phase 5](phase-5-governance-v1-ga.md) | Governance + v1 GA | COMPLETE |
| [Phase 6](phase-6-v2-expansion.md) | v2 expansion (Performance/Security/A11y/Visual/Learning) | COMPLETE |
| [Phase 7](phase-7-v3-enterprise.md) | v3 enterprise (multi-tenant, federated KG, marketplace) | IN PROGRESS |

## Execution Order

```
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7
```

Each phase:
1. Implements the in-scope agents + infra + tests.
2. Must pass **all prior phase tests** with zero regressions.
3. Verifies via the test/verification criteria listed in its plan.

## Top-Level Architecture

- **Multi-cloud**: AWS (CDK), GCP (cdktf), Modal (native SDK).
- **Portability layer**: agents never import cloud SDKs directly; all access via `intelliqx-*` libs.
- **Storage**: object store (S3/GCS/modal.Volume) + zvec (vector) + Parquet+DuckDB (KG).
- **Events**: Pub/Sub semantics (EventBridge+SQS / Pub/Sub / modal.Queue).
- **LLM**: Bedrock / Vertex AI / vLLM or LiteLLM — selected per cloud via `intelliqx-llm`.

## Top-Level Decisions Locked

See `/docs/adr/` (ADRs 0001–0011) and Phase 0 plan.