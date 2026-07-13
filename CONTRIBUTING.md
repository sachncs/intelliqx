# Contributing to intelliqx

Thanks for your interest in contributing! This document covers
local development setup, the pull request process, and our coding
standards.

## Development setup

### Prerequisites

- **Python 3.12+** (3.13 is not yet supported — see `pyproject.toml`)
- **[uv](https://docs.astral.sh/uv/)** (workspace + lockfile manager)
- **Docker** (optional, for the local infra profile and end-to-end tests)

### Clone and install

```bash
git clone https://github.com/sachncs/intelliqx.git
cd intelliqx
uv sync --all-packages
```

The workspace installs all 15 libraries, the 29 agent implementations,
and the dev dependency group (ruff, mypy, black, vulture, pytest).

### Verify the install

```bash
# Run the unit suite (no cloud credentials required)
uv run pytest tests/unit -q

# Run the four CI checks
uv run ruff check .
uv run black --check .
uv run mypy libs agents
uv run vulture libs agents tests .vulture-whitelist
```

All four must pass before you open a PR.

## Project layout

```
intelliqx/
├── libs/                  15 independent libraries (one package per concern)
├── agents/                29 agent implementations
├── tests/                 unit, integration, contract, e2e, cross_cloud
├── docs/                  ADRs, architecture, per-phase plans
├── .github/workflows/     CI definitions
└── pyproject.toml         Workspace + dev dependency definitions
```

Each library under `libs/` is independently installable and has its
own `pyproject.toml`. Cross-library imports are explicit (e.g.
`intelliqx_state` imports from `intelliqx_core`) and must be
declared as a workspace dependency in the importer's `pyproject.toml`.

## Adding a new library

1. Create `libs/intelliqx-<name>/pyproject.toml` with the workspace
   member declaration.
2. Add `intelliqx-<name> = { workspace = true }` under
   `[tool.uv.sources]` in the root `pyproject.toml`.
3. Add the new path under `[tool.uv.workspace] members = [...]` in
   the root `pyproject.toml`.
4. Run `uv sync --all-packages` to refresh the lockfile.
5. Add the library to the CI jobs' `uv sync` steps (no change needed
   if you use `--all-packages`).

## Adding a new agent

1. Choose a category directory (`coordination`, `intelligence`,
   `execution`, or `governance`) and add a new `.py` file.
2. Subclass `intelliqx_agents.base.AgentBase` with `INPUT_MODEL`,
   `OUTPUT_MODEL`, and a `META` class attribute using
   `AgentCategory.<CATEGORY>`.
3. Register the agent in `agents/__init__.py:register_all` and
   `register_compute_handlers`.
4. Add a test file under `tests/unit/test_<category>_<agent>.py`.
5. Add a row to `docs/architecture/agent-catalog.md`.
6. Open a PR — the test file and catalog entry are required for
   merge.

## Coding standards

### Style

- **Line length:** 100 (enforced by `black` and `ruff`).
- **Quotes:** double quotes.
- **Naming:** Pydantic models `PascalCase`; modules and functions
  `snake_case`; private members use Python name-mangling
  (`__name`).
- **Async first:** every public I/O method is `async def`. Blocking
  SDK calls are offloaded via `asyncio.to_thread`.
- **Frozen where possible:** value objects (e.g. `TenantContext`,
  `CloudConfig`) use `ConfigDict(frozen=True)` so they cannot be
  mutated mid-flight.

### Lint and type-check

- `ruff check .` must pass.
- `black --check .` must pass.
- `mypy libs agents` must pass with the configured `strict_optional`,
  `warn_unused_ignores`, and `no_implicit_optional`.
- `vulture libs agents tests .vulture-whitelist` must pass.

All four are enforced as separate CI jobs.

### Docstrings

Every public module, class, function, and method has a Google-style
docstring. Per-Pydantic-model `Attributes:` sections are required for
every input/output model. See any agent file (e.g.
`agents/coordination/planner.py`) for the canonical style.

### Testing

- Unit tests live under `tests/unit/` and follow the
  `test_<module>.py` naming convention.
- Cross-cloud parity tests live under `tests/cross_cloud/`.
- Every agent has at least one unit test (an `AgentMeta` check plus a
  smoke test that calls the `run` method with a minimal payload).
- All 415 tests must pass before merge.

## Pull request process

1. **Branch from `master`.** Use a descriptive branch name
   (`feat/vector-cosine`, `fix/mypy-redis`, `docs/agent-catalog`).
2. **Keep commits atomic.** Each commit should compile and pass
   tests in isolation. Use the Conventional Commits style
   (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`);
   breaking changes use the `!` suffix.
3. **Update the changelog** if your change is user-visible. Add a
   bullet under `[Unreleased]` in `CHANGELOG.md`.
4. **Add a test** for any non-trivial change. Bug fixes should
   include a regression test that fails before the fix.
5. **Open the PR against `master`.** The PR description should
   include:
   - A one-line summary
   - The motivation (link to an issue if applicable)
   - A list of changed files / libraries
   - Test results (`uv run pytest tests/unit -q` output is enough
     for most PRs)
6. **Wait for CI.** The four jobs (`format`, `lint`, `typecheck`,
   `dead-code`) plus the `test` matrix must all be green.
7. **Address review feedback** with follow-up commits (don't
   force-push during review).

## Release process

1. Bump the version in `pyproject.toml` (workspace root).
2. Move the `[Unreleased]` section in `CHANGELOG.md` into a new
   dated version header.
3. Tag the release: `git tag -a v<X.Y.Z> -m "v<X.Y.Z>"` and push
   with `git push --tags`.
4. The CI workflow will run the full test matrix against the tag.

## Questions?

Open an issue or email **sachncs@gmail.com**.
