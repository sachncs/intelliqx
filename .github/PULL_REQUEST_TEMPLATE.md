## Summary

<!-- One-paragraph description of what this PR changes and why. -->

## Linked issues

<!-- `Fixes #123`, `Closes #456`, etc. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation

## CI jobs

The following CI jobs must pass before merge:

- [ ] `format` — `ruff format --check .`
- [ ] `lint` — `ruff check .`
- [ ] `typecheck` — `mypy libs agents`
- [ ] `dead-code` — `vulture libs agents tests .vulture-whitelist`
- [ ] `test` — unit + contract test matrices
- [ ] `coverage` — coverage gate at 70%
- [ ] `docker-compose-validate` — `docker compose config` validates

## Checklist

- [ ] I have read [CONTRIBUTING.md](../CONTRIBUTING.md)
- [ ] I have added tests for my change (or explained why none are needed)
- [ ] I have updated the docs (or explained why no doc change is needed)
- [ ] The CHANGELOG is updated under `[Unreleased]` for user-visible changes
- [ ] All new and existing tests pass locally
- [ ] The change does not introduce a new dependency without justification
