"""Repository metadata model and filesystem scanner.

Scans a repository root to detect Python files and count
their approximate lines of code. The detected metadata
populates the ``RepositoryMetadata`` field of the
``SoftwareGraph``.
"""

from __future__ import annotations

import os
from pathlib import Path

from intelliqx_graph.models import RepositoryMetadata

PYTHON_EXTENSIONS: frozenset[str] = frozenset({".py", ".pyi"})

BUILD_SYSTEM_FILES: dict[str, str] = {
    "pyproject.toml": "python",
    "setup.py": "python",
    "setup.cfg": "python",
}

DIRECTORIES_TO_SKIP: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        "node_modules",
        "vendor",
        "dist",
        "build",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "target",
        "coverage",
        ".tox",
        ".eggs",
    }
)


def collect_repository_metadata(root: str | Path) -> RepositoryMetadata:
    """Scan a repository root and produce metadata.

    Counts Python files, sums their approximate line counts,
    and records any Python build-system files at the root.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    total_files = 0
    total_lines = 0
    build_systems: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in DIRECTORIES_TO_SKIP and not d.endswith(".egg-info")
        ]
        for filename in filenames:
            filepath = Path(dirpath) / filename
            if filepath.suffix.lower() not in PYTHON_EXTENSIONS:
                continue
            total_files += 1
            try:
                if filepath.stat().st_size < 1_000_000:
                    total_lines += sum(
                        1 for _ in filepath.open("r", encoding="utf-8", errors="ignore")
                    )
            except OSError:
                pass
        for filename in filenames:
            if filename in BUILD_SYSTEM_FILES and BUILD_SYSTEM_FILES[filename] not in build_systems:
                build_systems.append(BUILD_SYSTEM_FILES[filename])

    return RepositoryMetadata(
        name=root.name,
        root_path=str(root),
        languages=["python"],
        frameworks=[],
        build_systems=build_systems,
        total_files=total_files,
        total_lines=total_lines,
    )


def get_language_for_file(file_path: str | Path) -> str:
    """Return ``"python"`` for ``.py`` / ``.pyi``, ``"unknown"`` otherwise."""
    ext = Path(file_path).suffix.lower()
    return "python" if ext in PYTHON_EXTENSIONS else "unknown"
