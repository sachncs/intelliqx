"""Repository contracts for terminal output."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (
    REPO_ROOT / "libs",
    REPO_ROOT / "agents",
    REPO_ROOT / "scripts",
    REPO_ROOT / "tests" / "fixtures",
)
LOGGING_IMPLEMENTATION = (
    REPO_ROOT
    / "libs"
    / "intelliqx-observability"
    / "src"
    / "intelliqx_observability"
    / "logging.py"
)
_OUTPUT_EXAMPLE = re.compile(r"\b(?:print|pprint)\s*\(")


def _python_files() -> list[Path]:
    return [
        path for root in SCAN_ROOTS for path in root.rglob("*.py") if path != LOGGING_IMPLEMENTATION
    ]


def _trees() -> list[tuple[Path, ast.Module]]:
    trees: list[tuple[Path, ast.Module]] = []
    for path in _python_files():
        trees.append((path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))))
    return trees


def _call_name(node: ast.Call) -> str:
    function = node.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return ""


@pytest.mark.contract
def test_first_party_python_has_no_direct_terminal_calls() -> None:
    violations: list[str] = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name in {"print", "pprint", "print_exc"}:
                violations.append(f"{path}:{node.lineno}: {name}")
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr not in {
                "write",
                "writelines",
            }:
                continue
            target = node.func.value
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "sys"
                and target.attr in {"stdout", "stderr"}
            ):
                violations.append(f"{path}:{node.lineno}: sys.{target.attr}.{node.func.attr}")
    assert not violations, "\n".join(violations)


@pytest.mark.contract
def test_readme_and_first_party_docstrings_have_no_output_examples() -> None:
    violations: list[str] = []
    for path in REPO_ROOT.rglob("*.md"):
        if any(
            part in {".git", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
            for part in path.parts
        ):
            continue
        if _OUTPUT_EXAMPLE.search(path.read_text(encoding="utf-8")):
            violations.append(str(path))

    for path, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            docstring = ast.get_docstring(node, clean=False)
            if docstring is not None and _OUTPUT_EXAMPLE.search(docstring):
                violations.append(f"{path}:{getattr(node, 'lineno', 1)}")
    assert not violations, "\n".join(violations)


@pytest.mark.contract
def test_loguru_sink_is_the_only_first_party_stream_writer() -> None:
    source = LOGGING_IMPLEMENTATION.read_text(encoding="utf-8")
    stderr_write = ".".join(("sys", "stderr", "write"))
    stdout_write = ".".join(("sys", "stdout", "write"))
    assert source.count(stderr_write) == 1
    assert stdout_write not in source
