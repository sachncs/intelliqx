# Phase 3 — Tier 2 Domain Intelligence Core

**Goal**: Implement the four core Tier 2 reasoning agents — Requirements Intelligence, Code Intelligence, Test Design, Critic — plus supporting Risk Assessment, Coverage Analysis, and Test Data scaffolding.

**Status**: PENDING

---

## 3.1 Scope

| Agent | Inputs | Outputs | Backing Data |
|---|---|---|---|
| Requirements Intelligence | PRD, stories, AC | Requirements graph + traceability matrix | KG (Parquet) |
| Code Intelligence | AST (tree-sitter), PRs, code | Impact graph, dependency graph | KG + zvec |
| Risk Assessment | Requirements + Code + historical defects | Risk score, regression priority, business impact | KG |
| Test Design | Requirements + Risk | Functional, boundary, negative, exploratory tests | zvec (templates) |
| Test Data | Requirements + Test Design | Synthetic, boundary, privacy-safe datasets | S3 / GCS / modal.Volume |
| Coverage Analysis | All above + execution results | Req / test / code coverage + gap report | KG + DynamoDB |
| Critic / Validator | Any agent output | Critique (consistency, hallucination, completeness) | zvec (rules) |

Deferred to Phase 6: Learning Agent, Prompt Management Agent.

## 3.2 Architecture

- All Tier 2 agents are **reasoning agents**: Lambda/Cloud Function/modal.Function + LiteLLM (per cloud).
- They write to KG (Parquet) and zvec; read from KG, zvec, and external sources (GitHub, Jira).
- Planner (Phase 1) invokes these via the Orchestrator.
- Critic runs as a guardrail after every Tier 2 agent output; failures trigger self-retry or human escalation.

## 3.3 Deliverables

- [ ] `agents/tier2/requirements_intel/` — PRD parser, entity extractor (LLM), traceability matrix writer.
- [ ] `agents/tier2/code_intel/` — tree-sitter AST ingestion, diff impact analyzer.
- [ ] `agents/tier2/risk_assessment/` — risk scorer (LLM-as-judge + heuristic).
- [ ] `agents/tier2/test_design/` — Gherkin + structured test spec generator.
- [ ] `agents/tier2/test_data/` — Faker-based synthetic data + boundary datasets.
- [ ] `agents/tier2/coverage_analysis/` — coverage aggregator.
- [ ] `agents/tier2/critic/` — output validator (rules + LLM).
- [ ] Schemas: `requirements.graph.v1`, `test.design.v1`, `risk.score.v1`, `critique.v1`.
- [ ] Eval datasets in `evals/tier2/` (goldens).
- [ ] Integration with Planner: a goal of `analyze_prd` produces Requirements Intel → Test Design chain.

## 3.4 Test/verification criteria

1. **Requirements Intel**: parse 5 synthetic PRDs (varied complexity); assert entities, relations, traceability matrix correctness ≥ 0.9 F1 vs goldens.
2. **Code Intel**: ingest 3 synthetic repos; produce impact graph; assert ≥ 0.85 precision on affected files for 10 PR scenarios.
3. **Risk Assessment**: 50 labeled historical defects → risk score AUC ≥ 0.75.
4. **Test Design**: 20 requirements → ≥ 3 tests per requirement (functional, boundary, negative) on average; ≥ 0.85 acceptance per golden.
5. **Test Data**: synthetic datasets pass validator (no real PII matches via Presidio).
6. **Critic**: catches 100% of planted hallucinations and 100% of schema violations.
7. **Coverage Analysis**: end-to-end pipeline (PRD → code → tests → coverage) yields consistent numbers across runs.
8. **All evals** registered with LangSmith-compatible format and runnable via `make eval tier=2`.

## 3.5 Out of scope

- Execution agents (Phase 4).
- Self-Healing, Visual, Accessibility, Performance, Security (Phase 6).
- Learning loop (Phase 6).

## 3.6 Risks

| Risk | Mitigation |
|---|---|
| tree-sitter grammars heavy in Lambda | Use Lambda container with custom image; cache grammars in `/tmp` |
| LLM hallucinations in requirements parsing | Critic + golden-eval regression |
| PII in synthetic data | Presidio + allowlist test |