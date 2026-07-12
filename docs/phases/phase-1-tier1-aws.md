# Phase 1 — Tier 1 Agents (AWS-First)

**Goal**: Implement the AI Coordination Layer end-to-end on AWS: Planner, Orchestrator, Memory Manager, Knowledge/RAG, Tool Manager. Prove the full Goal → Plan → Execute → Result loop with one downstream agent (the Smoke Agent).

**Status**: COMPLETE

### Implementation summary
- Planner Agent (`agents/tier1/planner.py`): deterministic template-based plan generation, validates DAG, applies cost-ceiling trimming, supports 5 goal templates.
- Orchestrator Agent (`agents/tier1/orchestrator.py`): in-process state machine mimicking Step Functions semantics — topological scheduling, parallel execution, exponential-backoff retries, event emission, run status persistence.
- Memory Manager Agent (`agents/tier1/memory_manager.py`): polymorphic dispatch over Put/Get/Search/Summarize/Forget; tenant-scoped keys; working state via Redis, episodic/semantic/code memory via object store.
- Knowledge/RAG Agent (`agents/tier1/knowledge_rag.py`): hybrid retrieval (zvec vector + DuckDB KG scan + lexical match on episodic memory); ingest API for documents.
- Tool Manager Agent (`agents/tier1/tool_manager.py`): 5 starter tools (github.issue, jira.ticket, slack.message, pagerduty.alert, local_shell); MCP-compatible registry; per-tool rate limiting.
- Step Functions ASL: `workflows/orchestrator.asl.json` mirrors the in-process orchestrator.
- AWS CDK scaffold: 5 stacks (Api, Compute, Event, Storage, Observability) ready for Phase 2 expansion.

---

## 1.1 Scope

| Agent | Input | Output | Storage | Compute |
|---|---|---|---|---|
| Planner Agent | Goal + KB context | `ExecutionPlan` (DAG) | S3 + Redis | Lambda (60s) |
| Orchestrator Agent | `ExecutionPlan` | Run status, retry policy, audit | DynamoDB + Step Functions | Step Functions state machine |
| Memory Manager Agent | (PUT/GET/SEARCH/SUMMARIZE) | Memory artifacts | Redis + DynamoDB + S3 + zvec | Lambda |
| Knowledge / RAG Agent | Query | Retrieved docs + KG triples | zvec + Parquet-on-S3 | Lambda |
| Tool Manager Agent | Tool request | Tool response | DynamoDB registry + Secrets Manager | Lambda |

## 1.2 Architecture

- **API Gateway** → `/v1/goals` (POST), `/v1/runs/{id}` (GET).
- **Step Functions** state machine `AQIPPlannerOrchestrator` with states:
  - `Planner` (Lambda) → emit `plan.generated` → store plan in S3 + Redis.
  - `ParallelAgentMap` → for each plan node, invoke target agent Lambda.
  - `WaitForCompletion` (Step Functions callback pattern).
  - `Critic` (Lambda) — optional in v1, deferred to Phase 3.
  - `PersistResults` (Lambda).
- **EventBridge** bus `aqip.bus` carries `goal.received`, `plan.generated`, `agent.invoked`, `agent.completed`, `agent.failed`, `run.completed`.
- **SQS** queues per agent with DLQ.
- **Redis (ElastiCache)** as the live blackboard.
- **DynamoDB** for run/plan/audit tables.
- **zvec + S3** for RAG embeddings.
- **Parquet on S3** for KG (DuckDB on Lambda container).

## 1.3 Deliverables

- [ ] `agents/tier1/planner/` — Agent implementation + prompts + tests.
- [ ] `agents/tier1/orchestrator/` — Step Functions ASL + Python CDK construct.
- [ ] `agents/tier1/memory_manager/` — CRUD/search API.
- [ ] `agents/tier1/knowledge_rag/` — Hybrid retriever (vector + KG + lexical).
- [ ] `agents/tier1/tool_manager/` — MCP gateway + 5 starter tools (GitHub, Jira, Slack, PagerDuty, LocalShell).
- [ ] `workflows/full_qa_workflow.asl.json` — full Tier-1 orchestration.
- [ ] `infra/aws/` — CDK app with stacks: `ApiStack`, `EventStack`, `ComputeStack`, `StorageStack`, `ObservabilityStack`.
- [ ] Seed data: sample PRD, sample code repo (toy).
- [ ] Local smoke test: runs the full loop against docker-compose infra (no AWS credentials).

## 1.4 Test/verification criteria

1. **Planner unit tests** (≥20 cases): goal → plan DAG; cycle detection; dependency satisfaction; SLA enforcement; cost ceiling enforcement.
2. **Orchestrator unit tests**: plan → Step Functions ASL JSON; retry policy correctness; DLQ wiring.
3. **Memory Manager**: PUT/GET/SEARCH round-trip; TTL expiration; summarization preserves key entities.
4. **RAG**: hybrid retriever recall ≥ 0.9 on synthetic corpus (1k docs, 100 queries, ground-truth triplets).
5. **Tool Manager**: all 5 starter tools pass mock-server contract tests; rate limiter enforces 429 after threshold.
6. **End-to-end smoke (local)**: submit `goal` → orchestrator → planner → 1 mock agent → result persisted → `/v1/runs/{id}` returns status `SUCCEEDED`.
7. **CDK synth**: `cdk synth` produces valid CloudFormation; stacks have no circular dependencies.
8. **Lint/type/test**: all green.

## 1.5 Out of scope

- GCP/Modal deployment (Phase 2).
- Critic agent (Phase 3).
- Any Tier 2/3/4 agent.

## 1.6 Risks

| Risk | Mitigation |
|---|---|
| Step Functions state size limit (256 KB) for large plans | Shard plan into sub-plans; orchestrator recursively invokes |
| DynamoDB hot partition on `run_id` | Use ULID + sort key `ts` |
| Lambda cold start too high for Planner (LLM-bound) | Provisioned concurrency in CDK; warmup ping via EventBridge schedule |