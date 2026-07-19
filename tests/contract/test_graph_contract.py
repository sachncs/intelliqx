"""Contract tests for the Python-only graph package."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from intelliqx_graph.operations import (
    build_software_graph,
    generate_code,
    optimize_graph,
    parse_repository,
    scan_repository,
)


def test_only_python_files_are_parsed(tmp_path: Path) -> None:
    """Non-Python files under the root must be ignored by ``parse_repository``."""
    (tmp_path / "good.py").write_text("def f(): return 1\n")
    (tmp_path / "good.pyi").write_text("def iface(x: int) -> int: ...\n")
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")
    (tmp_path / "main.ts").write_text("export function main() {}\n")
    (tmp_path / "Main.java").write_text("class Main {}\n")
    (tmp_path / "lib.rs").write_text("fn main() {}\n")
    (tmp_path / "app.js").write_text("function main() {}\n")
    (tmp_path / "README.md").write_text("# nope\n")

    result = parse_repository(str(tmp_path))
    file_paths = {entry["file_path"] for entry in result["entities"]}

    assert all(fp.endswith((".py", ".pyi")) for fp in file_paths)
    assert result["errors"] == []
    assert any(fp.endswith(".py") and fp.endswith("good.py") for fp in file_paths)


def test_parse_repository_skips_unsupported_extensions(tmp_path: Path) -> None:
    """Files with extensions outside ``.py`` / ``.pyi`` must not raise errors."""
    (tmp_path / "broken.go").write_text("not really go")
    (tmp_path / "broken.rs").write_text("not really rust")
    (tmp_path / "broken.java").write_text("not really java")

    result = parse_repository(str(tmp_path))

    assert result["entities"] == []
    assert result["errors"] == []


def test_scan_repository_only_counts_python_files(tmp_path: Path) -> None:
    """``scan_repository`` reports only ``python`` in its languages list."""
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.pyi").write_text("y: int\n")
    (tmp_path / "c.go").write_text("package main\n")
    (tmp_path / "d.ts").write_text("export const x = 1;\n")

    metadata = scan_repository(str(tmp_path))

    assert metadata["languages"] == ["python"]
    assert metadata["total_files"] == 2


def test_graph_package_runtime_dependencies_are_minimal() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "libs" / "intelliqx-graph" / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == ["pydantic>=2.8", "networkx>=3.4"]


def test_public_operation_names_have_no_tool_suffix() -> None:
    """All top-level SGIR pipeline operations are exposed without ``_tool`` suffix."""
    expected = {
        scan_repository.__name__,
        parse_repository.__name__,
        build_software_graph.__name__,
        optimize_graph.__name__,
        generate_code.__name__,
    }
    assert expected == {
        "scan_repository",
        "parse_repository",
        "build_software_graph",
        "optimize_graph",
        "generate_code",
    }


def test_graph_build_rejects_invalid_entities(tmp_path: Path) -> None:
    metadata = scan_repository(str(tmp_path))
    with pytest.raises(ValueError):
        build_software_graph(metadata, [{"name": "broken"}])


@pytest.mark.parametrize("language", ["go", "rust", "typescript", "java"])
def test_backend_registry_is_python_only(language: str) -> None:
    """Only Python is registered as a code-generation backend."""
    import pytest
    from intelliqx_graph.backends import get_backend

    with pytest.raises(ValueError):
        get_backend(language)
