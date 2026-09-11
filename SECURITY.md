# Security

## Supported versions

| Version | Supported          |
|---------|--------------------|
| latest  | :white_check_mark: |
| older   | :x:                |

Only the latest released version receives security fixes. Please upgrade
before reporting an issue.

## Reporting a vulnerability

**Please do not file a public issue.** Use GitHub's
[private vulnerability reporting](https://github.com/sachncs/intelliqx/security/advisories/new)
for this repository, or — if private reporting is unavailable — email
**sachncs@gmail.com**.

## Scope

The following packages are in scope for security disclosures:

* `intelliqx-service` — the FastAPI service exposed at
  `INTELLIQX_API_TOKEN`-protected `/v1/runs` endpoints.
* `intelliqx-storage`, `intelliqx-state`, `intelliqx-events`,
  `intelliqx-compute` — the in-process adapters and runtime that
  every agent exercises.

Third-party adapters and example agents are out of scope; report
issues in their upstream projects instead.

## Response SLA

- Acknowledgement within **3 business days**.
- Triage and severity assessment within **7 business days**.
- Fix timeline negotiated based on severity and exploitability.

Thank you for helping keep `intelliqx` and its users safe.
