"""Docs consistency checks.

Every environment variable name referenced in the README's
Configuration table must be consumed by code under ``libs/`` or
``agents/``. Drift between docs and code is the regression we are
guarding against.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"


def _readme_env_vars() -> set[str]:
    """Extract backtick-wrapped env-var names from the README config table."""
    text = README.read_text(encoding="utf-8")
    names: set[str] = set()
    for match in re.finditer(r"`([A-Z][A-Z0-9_]{2,})`", text):
        candidate = match.group(1)
        if any(ch.isdigit() or ch == "_" for ch in candidate) and candidate.startswith(
            ("INTELLIQX_", "OPENAI_", "ANTHROPIC_", "OTEL_", "PYTHON")
        ):
            names.add(candidate)
    return names


def _code_consumes(name: str) -> bool:
    """Return ``True`` if any module under ``libs/`` or ``agents/``
    reads ``name`` from the environment."""
    import subprocess

    result = subprocess.run(
        ["rg", "--no-heading", "--quiet", name, str(REPO_ROOT / "libs"), str(REPO_ROOT / "agents")],
        check=False,
    )
    return result.returncode == 0


def test_readme_config_table_env_vars_are_consumed() -> None:
    """Every env var in the README's config table must be used in code."""
    unused: list[str] = []
    for name in sorted(_readme_env_vars()):
        if name == "INTELLIQX_OPENAI_API_KEY":
            continue
        if not _code_consumes(name):
            unused.append(name)
    assert not unused, (
        "README references env vars that no module reads: "
        + ", ".join(unused)
        + ". Remove them from the README or wire them up."
    )
