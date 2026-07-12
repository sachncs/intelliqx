# AQIP Cost Model

Per-invocation USD cost estimates used by the Planner to enforce
the ``cost_ceiling_usd`` goal constraint. Values live in
`_node_cost` in `agents/tier1/planner.py`; they are tuned for AWS
Bedrock + Lambda pricing and are *estimates*, not billable
amounts.

## Reference table

| Agent | Estimated cost (USD) | Notes |
|---|---:|---|
| `planner` | 0.05 | Deterministic template lookup; negligible compute. |
| `orchestrator` | 0.02 | DAG scheduling, retries, event emission. |
| `memory_manager` | 0.01 | One storage call per operation. |
| `knowledge_rag` | 0.08 | Embed query + vector search + KG LIKE + lexical scan. |
| `tool_manager` | 0.02 | Tool invocation + rate-limit bucket. |
| `requirements_intel` | 0.20 | Regex extraction; cheap but full PRD size. |
| `code_intel` | 0.15 | Regex import extraction; scales with LOC. |
| `test_design` | 0.20 | Per-requirement test generation. |
| `critic` | 0.10 | Optional jsonschema + rule evaluation. |
| `execution` | 0.30 | Per-step HTTP, scales with test count. |
| `self_healing` | 0.10 | LLM ranking; one call per failed selector. |
| `failure_analysis` | 0.10 | Pure heuristic; no LLM. |
| `environment` | 0.50 | uvicorn boot + health poll. |
| `design_intel` | 0.08 | DOM regex parsing. |
| `reporting` | 0.05 | Markdown + JSON synthesis. |
| `release_readiness` | 0.10 | Pure score computation. |
| (default for any unlisted agent) | 0.10 | Conservative fallback. |

## How the cost ceiling is enforced

1. The Planner produces a plan from the goal template.
2. The plan's total cost is computed by summing the per-node
   estimates above.
3. If the total exceeds ``cost_ceiling_usd`` (default 50.0,
   overridable per goal), the Planner runs
   :func:`agents.tier1.planner._trim_to_cost`, which drops nodes
   (optional first, then by descending cost) until the total
   fits. The trim propagates to transitive dependents, so
   "required" nodes that depended on dropped "optional" nodes
   are also dropped.
4. The trimmed DAG is re-validated before the plan is returned.

## Re-calibrating

Production deployments should re-calibrate the table against
their actual bills. A simple approach:

1. Run a representative plan end-to-end.
2. Tag every agent invocation with its measured cost (the
   metrics layer already records duration; add token counts and
   per-invocation prices from the LLM provider's billing API).
3. Update the per-agent ``base`` dict in `_node_cost`.

The table is intentionally a small dict; re-calibration is a
matter of editing one constant.
