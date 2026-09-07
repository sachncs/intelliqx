# IntelliqX — Master Implementation Plan

## Overview

This directory contains the per-phase implementation plans for the Autonomous QA Intelligence Platform (IntelliqX).

## Phase Index

| Phase | Scope | Status |
|---|---|---|
| [Phase 0](phase-0-foundations.md) | Foundations — monorepo, libs, infra, CI | COMPLETE |
| [Phase 3](phase-3-intelligence-core.md) | Intelligence domain core | COMPLETE |
| [Phase 4](phase-4-execution.md) | Execution core | COMPLETE |
| [Phase 5](phase-5-governance-v1-ga.md) | Governance + v1 GA | COMPLETE |
| [Phase 6](phase-6-v2-expansion.md) | v2 expansion (Performance/Security/A11y/Visual/Learning) | COMPLETE |

## Execution Order

```
Phase 0 → Phase 3 → Phase 4 → Phase 5 → Phase 6
```

Each phase:
1. Implements the in-scope agents + infra + tests.
2. Must pass **all prior phase tests** with zero regressions.
3. Verifies via the test/verification criteria listed in its plan.

## Top-Level Architecture

- **Storage**: in-memory object store + zvec (vector) + Parquet+DuckDB (KG).
- **Events**: in-process Pub/Sub-style bus with DLQ semantics.
- **LLM**: Fake (default) or MiniMax via litellm — selected via `intelliqx-llm` (see ADR-0012).

## Top-Level Decisions Locked

See `/docs/adr/` (ADRs 0001–0012) and Phase 0 plan.
