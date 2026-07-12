# AQIP — Master Implementation Plan

## Overview

This directory contains the per-phase implementation plans for the Autonomous QA Intelligence Platform (AQIP).

## Phase Index

| Phase | Scope | Status |
|---|---|---|
| [Phase 0](phase-0-foundations.md) | Foundations — monorepo, libs, infra, CI | PENDING |
| [Phase 1](phase-1-tier1-aws.md) | Tier 1 agents on AWS | PENDING |
| [Phase 2](phase-2-multicloud.md) | Tier 1 multi-cloud parity (GCP + Modal) | PENDING |
| [Phase 3](phase-3-tier2-core.md) | Tier 2 domain intelligence core | PENDING |
| [Phase 4](phase-4-tier3-execution.md) | Tier 3 execution core | PENDING |
| [Phase 5](phase-5-tier4-v1-ga.md) | Tier 4 governance + v1 GA | PENDING |
| [Phase 6](phase-6-v2-expansion.md) | v2 expansion (Performance/Security/A11y/Visual/Learning) | PENDING |
| [Phase 7](phase-7-v3-enterprise.md) | v3 enterprise (multi-tenant, federated KG, marketplace) | PENDING |

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
- **Portability layer**: agents never import cloud SDKs directly; all access via `aqip-*` libs.
- **Storage**: object store (S3/GCS/modal.Volume) + zvec (vector) + Parquet+DuckDB (KG).
- **Events**: Pub/Sub semantics (EventBridge+SQS / Pub/Sub / modal.Queue).
- **LLM**: Bedrock / Vertex AI / vLLM or LiteLLM — selected per cloud via `aqip-llm`.

## Top-Level Decisions Locked

See `/docs/adr/` (ADRs 0001–0010) and Phase 0 plan.