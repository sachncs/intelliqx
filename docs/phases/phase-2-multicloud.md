# Phase 2 — Tier 1 Multi-Cloud Parity (GCP + Modal)

**Goal**: Run the same Tier 1 agents unchanged on GCP and Modal. Prove parity via cross-cloud integration tests.

**Status**: PENDING

---

## 2.1 Scope

| Cloud | Compute | Event Bus | Storage | State | LLM | IaC |
|---|---|---|---|---|---|---|
| AWS | Lambda + Step Functions (Phase 1) | EventBridge + SQS | S3 | ElastiCache | Bedrock | CDK |
| GCP | Cloud Functions gen 2 + Workflows | Pub/Sub | GCS | Memorystore | Vertex AI | cdktf |
| Modal | `modal.Function` | `modal.Queue` | `modal.Volume` | `modal.Dict` / Upstash | vLLM or LiteLLM | Modal SDK |

## 2.2 Architecture

- Each Tier 1 agent containerized once via shared `Dockerfile.agent`.
- `INTELLIQX_CLOUD` env var selects adapter at runtime.
- Each cloud has its own IaC stack that produces identical logical resources.
- `infra/cross-cloud/` parent program (Pulumi, optional) orchestrates all three.

## 2.3 Deliverables

- [ ] `infra/gcp/` — cdktf Python project: stacks for API, Events, Compute, Storage, Observability.
- [ ] `infra/modal/` — Modal app definition with `modal.Stub(app_name="intelliqx-tier1")`.
- [ ] GCP adapters in all libs: `intelliqx-events/gcp.py`, `intelliqx-storage/gcp.py`, `intelliqx-vector/gcp.py`, `intelliqx-state/gcp.py`, `intelliqx-llm/vertex.py`, `intelliqx-compute/gcp.py`.
- [ ] Modal adapters in all libs.
- [ ] Cloud Run service for Orchestrator (replaces Step Functions on GCP).
- [ ] Modal `modal.Function` for Orchestrator with `@modal.enter()` snapshot.
- [ ] Cross-cloud test suite: same Goal → Plan → Result runs against all three clouds in CI (mocked credentials; live adapter tests in nightly).

## 2.4 Test/verification criteria

1. **Adapter parity**: every interface has ≥3 test cases per adapter (4 adapters × N tests).
2. **Cross-cloud integration**: a pytest suite tagged `@cross_cloud` runs the smoke goal against each cloud's in-memory fakes; asserts identical plan and result shape.
3. **GCP cdktf synth**: produces valid Terraform; `tofu validate` exits 0.
4. **Modal app loads**: `modal app lookups` succeeds (CI-only; doesn't deploy).
5. **Adapter swap test**: change `INTELLIQX_CLOUD` from `aws` to `gcp` to `modal` to `local`; the same agent code produces the same structured output.

## 2.5 Out of scope

- Performance, Security, Accessibility, Visual agents (Phase 6).
- Real GCP/Modal credentials (CI uses fakes).

## 2.6 Risks

| Risk | Mitigation |
|---|---|
| Bedrock ≠ Vertex AI ≠ vLLM in capability | Capability matrix enforced by `intelliqx-llm`; agents degrade gracefully |
| Cloud Functions gen 2 still has cold start issues | Min-instances 1 for Orchestrator on GCP |
| Modal `modal.Queue` retention limits (24h default) | DLQ to Upstash Redis for long retention |