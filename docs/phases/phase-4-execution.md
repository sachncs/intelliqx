# Phase 4 — Tier 3 Execution Core

**Goal**: Implement the execution backbone — Environment Agent, Execution Agent, Self-Healing Agent, Failure Analysis Agent — plus Design Intelligence supporting agent. Enable end-to-end Goal → Plan → Tests → Executed → Healed → Reported flow.

**Status**: PENDING

---

## 4.1 Scope

| Agent | Compute | Inputs | Outputs |
|---|---|---|---|
| Environment | Lambda | Plan, infra config | `env.ready` event + env handle |
| Design Intelligence | Lambda | DOM snapshot, a11y tree | UI semantic graph |
| Execution | Fargate / Cloud Run / modal.Function (browser session) | Test spec, env handle | Test results + artifacts (S3) |
| Self-Healing | Lambda | Failed selector + DOM | New selector + confidence score |
| Failure Analysis | Lambda | Failure record + history | Root cause + classification (infra/product/flake) |

Deferred to Phase 6: Visual Regression, Accessibility, Performance, Security.

## 4.2 Architecture

- **Environment** provisions ephemeral envs via Terraform modules + Docker images.
- **Execution** uses Playwright in a long-lived Fargate/Cloud Run/Modal container with `@enter`-snapshot browser reuse (Modal) or warm-pool (Fargate).
- **Self-Healing** is a fast-path Lambda invoked on Execution failure.
- **Failure Analysis** invoked on unhealable failures; writes classification to KG.

## 4.3 Deliverables

- [ ] `agents/execution/environment/` — env provisioner (k8s manifest generator + terraform).
- [ ] `agents/execution/design_intel/` — DOM/a11y tree semantic extractor.
- [ ] `agents/execution/execution/` — Playwright runner; artifact uploader; event emitter.
- [ ] `agents/execution/self_healing/` — selector repair (LLM + heuristics).
- [ ] `agents/execution/failure_analysis/` — root cause classifier.
- [ ] `workflows/full_qa_workflow.asl.json` updated to include Tier 3.
- [ ] Reference web app under `tests/fixtures/reference_app/` (multi-page, accessible, intentionally broken in places for healing tests).
- [ ] E2E test: full pipeline runs against reference app locally; ≥ 80% of "broken" tests heal successfully.

## 4.4 Test/verification criteria

1. **Environment**: provisions and tears down a test app in <2 minutes locally; validates health endpoints.
2. **Execution**: runs 50 Playwright tests locally; emits all required events; uploads artifacts to local object store.
3. **Self-Healing**: 20 planted broken selectors → ≥ 80% auto-heal; remaining flagged for human review.
4. **Failure Analysis**: 30 labeled failures → ≥ 0.85 macro-F1 across infra/product/flake classes.
5. **Design Intelligence**: DOM snapshots → semantic graph with ≥ 0.9 F1 vs golden on reference app.
6. **E2E pipeline** (`tests/e2e/test_full_pipeline.py`): green; covers Goal → Plan → Test Design → Execute → Heal → Report.
7. **All existing tests still green**; no regressions in Phases 0–3.

## 4.5 Out of scope

- Real browsers in CI (use Playwright headless locally; CI runs with `--workers=2` and `--headed=false`).
- iOS/Android execution (deferred to v3 enterprise).

## 4.6 Risks

| Risk | Mitigation |
|---|---|
| Playwright flakiness on local macOS | Retry policy in Execution; lock browsers via Playwright version pin |
| Self-Healing LLM cost on every retry | Cache healing attempts per selector; escalate only on miss |
| Long browser sessions leak memory | `@modal.enter()` snapshot reload; Fargate task recycling every N runs |