# Phase 7 — v3 Enterprise

**Goal**: Convert AQIP into a multi-tenant enterprise SaaS: federated knowledge, portfolio analytics, marketplace, cross-region, predictive quality, BYO-LLM. Certify v3 GA.

**Status**: PENDING

---

## 7.1 Scope

| Capability | Description |
|---|---|
| Multi-tenant SaaS | Per-tenant isolation in zvec, KG, Redis, queues; tenant-aware auth and quotas |
| Federated knowledge graphs | Cross-repo intelligence; tenant-defined sharing policies |
| Cross-region | Active-active in AWS `us-east-1` + `eu-west-1` + GCP `us-central1` |
| Portfolio analytics | Org-wide quality dashboards; trend analysis; SLA rollups |
| Predictive quality | ML model predicts defect density / release risk from historical data |
| Marketplace | Custom agent SDK + verified marketplace of community agents |
| BYO-LLM | Tenants bring their own Bedrock/Vertex/vLLM endpoint; platform routes per tenant |
| Compliance packs | SOC2, ISO27001, HIPAA, GDPR — config-driven evidence collection |

## 7.2 Architecture

- **Tenant namespace**: every zvec index, KG partition, Redis key, S3 prefix scoped by `tenant_id`.
- **Federation**: KG shards per tenant + global cross-tenant index layer with row-level security.
- **Cross-region**: event replicator across regions; orchestrator state in DynamoDB Global Tables / Firestore / modal.Dict replicated.
- **Marketplace**: agent registry with signed manifests; sandboxed runtime per agent; revenue share.
- **Predictive quality**: feature store (DuckDB or Feast on Parquet) → XGBoost/LightGBM model trained per tenant + global.

## 7.3 Deliverables

- [ ] Tenant isolation middleware (`aqip-tenant/`).
- [ ] Federated KG query API.
- [ ] Cross-region replicator (configurable per topic).
- [ ] Portfolio analytics dashboards.
- [ ] Predictive quality model + serving agent.
- [ ] Agent SDK (`aqip-sdk/`) + marketplace UI stub.
- [ ] BYO-LLM adapter router.
- [ ] Compliance pack framework + 2 reference packs (SOC2, GDPR).
- [ ] v3 GA release notes.

## 7.4 Test/verification criteria

1. **Multi-tenant isolation**: zero cross-tenant data leakage in 100 random cross-tenant attempts.
2. **Federated KG**: cross-tenant query respects allowlist; query denied otherwise.
3. **Cross-region**: goal submitted in region A → completed in region B with identical result.
4. **Portfolio analytics**: 3-tenant simulated portfolio produces correct aggregates.
5. **Predictive quality**: AUC ≥ 0.75 on synthetic defect dataset.
6. **Marketplace**: third-party agent loads, runs in sandbox, emits standard events.
7. **BYO-LLM**: tenant routes to custom endpoint; cost + latency tracked.
8. **Compliance**: SOC2 evidence pack produced for simulated audit period.
9. **All prior tests still green**; **tag `v3.0.0`** cut.

## 7.5 Risks

| Risk | Mitigation |
|---|---|
| Tenant leakage via shared infra | Property tests + fuzz tests + per-request tenant check |
| Marketplace agents compromise platform | Sandboxed runner (subprocess + seccomp), resource quotas |
| Predictive model bias | Per-tenant training; bias monitoring |
| Cross-region consistency | Tunable consistency modes (eventual / strong per topic) |