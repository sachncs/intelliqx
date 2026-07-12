# ADR-0001: Python 3.12 monorepo with uv workspaces

- **Status**: Accepted
- **Context**: IntelliqX needs a consistent dependency model across many libraries and agents while remaining serverless-friendly across AWS, GCP, and Modal.
- **Decision**: Use Python 3.12 in a uv workspace monorepo. Each library under `libs/intelliqx-*` is an independent package; `agents/` and `services/` consume them via workspace sources.
- **Consequences**:
  - Pros: deterministic resolution, fast installs, no virtualenv sprawl, native lockfile.
  - Cons: contributors must use `uv`; non-uv workflows need a thin pip-compatible fallback.

## References
- Phase 0 plan: `docs/phases/phase-0-foundations.md`