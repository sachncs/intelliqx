# Phase 6 — v2 Expansion

**Goal**: Add the full quality-dimension coverage (Performance, Security, Accessibility, Visual Regression), complete the feedback loop (Learning, Prompt Management, Cost Optimization), and ship v2 GA.

**Status**: COMPLETE

---

## 6.1 Scope

| Agent | Type |
|---|---|
| Visual Regression | Pixel + LLM visual diff |
| Accessibility | WCAG, keyboard, ARIA, contrast |
| Performance | Load/stress/spike/endurance/scalability (k6/Locust) |
| Security | SAST (regex subset), DAST header probe, dep scan, secrets (gitleaks subset) |
| Coverage Analysis (final) | Already in Phase 3, extended here with Phase 4 + 6 outputs |
| Learning | Prompt/plan/healing/prioritization improver |
| Prompt Management | Versions, A/B tests, bandit routing |
| Cost Optimization | Compute right-sizing, schedule, parallel efficiency |

## 6.2 Architecture

- **Performance** uses k6 (preferred) or Locust in a long-running process; emits SLO breaches.
- **Security** runs SAST/secret/dep on source files; DAST header probe against the live env.
- **Visual Regression** compares screenshots baseline vs current; LLM visual diff for semantic equivalence.
- **Accessibility** uses axe-core + custom checks.
- **Learning** consumes run history + critic feedback → updates prompt rankings, healing priors, prioritization weights.
- **Prompt Management** A/B tests prompts; bandit routing picks winners.
- **Cost Optimization** runs daily; recommends right-sizing.

## 6.3 Deliverables

- [x] `agents/execution/visual_regression/` — pixel diff + LLM diff.
- [x] `agents/execution/accessibility/` — axe + keyboard.
- [x] `agents/execution/performance/` — k6 runner; SLO definitions.
- [x] `agents/execution/security/` — SAST/DAST/dep/secrets checks.
- [x] `agents/intelligence/learning/` — feedback loop.
- [x] `agents/intelligence/prompt_management/` — versions + bandit.
- [x] `agents/execution/cost_optimization/` — analyzer + recommender.
- [x] Reference app extended with performance + a11y + visual baselines.
- [x] v2 GA release notes.

## 6.4 Test/verification criteria

1. **Visual Regression**: 20 baseline-vs-candidate scenarios; pixel diff + LLM diff agree ≥ 0.85.
2. **Accessibility**: axe-core finds planted violations; report includes remediation hints.
3. **Performance**: k6 runs against local target; SLO breaches flow to Reporting + Release Readiness.
4. **Security**: planted SAST/secret/dep issues found ≥ 0.9 recall; baseline header scan runs in <10 min locally.
5. **Learning**: feedback loop improves healing success rate by ≥ 10% on synthetic history.
6. **Prompt Management**: A/B test detects ≥ 5% prompt-quality delta with p < 0.05 on synthetic eval.
7. **Cost Optimization**: produces actionable recommendations on a 30-day synthetic run history.
8. **All prior tests still green**; **tag `v2.0.0`** cut.

## 6.5 Out of scope

- Multi-tenant SaaS, federated KG.

## 6.6 Risks

| Risk | Mitigation |
|---|---|
| k6 image large | Multi-stage build; cached layer |
| Bandit routing needs history | Cold-start with uniform random; warmup window |
