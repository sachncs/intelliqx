# ADR-0006: IaC — AWS CDK, GCP cdktf, Modal native SDK

- **Status**: Accepted
- **Context**: Each cloud has its own IaC ecosystem; uniformity matters for cross-cloud parity.
- **Decision**:
  - AWS: AWS CDK in Python.
  - GCP: CDK for Terraform (cdktf) in Python — same CDK pattern as AWS.
  - Modal: Modal native Python SDK (`modal deploy`) — Modal deployment is itself Pythonic.
  - Optional Pulumi parent program orchestrates all three for cross-cloud releases.
- **Consequences**:
  - Pros: CDK consistency for AWS/GCP; native tools used where they shine (Modal).
  - Cons: Three IaC toolchains; mitigated by shared config under `config/cloud_profiles/`.

## References
- Phase 0 / 2 plans