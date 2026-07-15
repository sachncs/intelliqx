"""Repository metadata model and filesystem scanner.

Scans a repository root to detect languages, frameworks, build
systems, and file counts. This metadata populates the
``RepositoryMetadata`` field of the ``SoftwareGraph``.
"""

from __future__ import annotations

import os
from pathlib import Path

from intelliqx_graph.models import RepositoryMetadata

# Extension-to-language mapping (common file extensions)
EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".swift": "swift",
    ".rb": "ruby",
    ".php": "php",
    ".scala": "scala",
    ".r": "r",
    ".R": "r",
}

# Build system detection files
BUILD_SYSTEM_FILES: dict[str, str] = {
    "pyproject.toml": "python",
    "setup.py": "python",
    "setup.cfg": "python",
    "package.json": "node",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "kotlin",
    "CMakeLists.txt": "cmake",
    "Makefile": "make",
    "Dockerfile": "docker",
    "docker-compose.yml": "docker",
    "docker-compose.yaml": "docker",
}

# Framework detection patterns
FRAMEWORK_MARKERS: dict[str, list[str]] = {
    "fastapi": ["fastapi"],
    "django": ["django"],
    "flask": ["flask"],
    "react": ["react", "next.config"],
    "vue": ["vue"],
    "angular": ["angular"],
    "spring": ["spring"],
    "rails": ["rails"],
    "gin": ["gin-gonic"],
    "fiber": ["gofiber"],
    "actix": ["actix-web"],
    "tokio": ["tokio"],
}

# Directories to skip during scanning
SKIP_DIRS = {
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
    "*.egg-info",
}


def scan_repository(root: str | Path) -> RepositoryMetadata:
    """Scan a repository root and produce metadata.

    Detects languages, frameworks, build systems, and counts files
    and approximate lines of code.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    languages: dict[str, int] = {}
    frameworks: list[str] = []
    build_systems: list[str] = []
    total_files = 0
    total_lines = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place
        dirnames[:] = [
            d
            for d in dirnames
            if d not in SKIP_DIRS and not d.endswith(".egg-info")
        ]

        for filename in filenames:
            total_files += 1
            filepath = Path(dirpath) / filename

            # Detect language by extension
            ext = filepath.suffix.lower()
            lang = EXTENSION_MAP.get(ext)
            if lang:
                languages[lang] = languages.get(lang, 0) + 1

            # Detect build system
            if filename in BUILD_SYSTEM_FILES:
                bs = BUILD_SYSTEM_FILES[filename]
                if bs not in build_systems:
                    build_systems.append(bs)

            # Count lines (approximate)
            try:
                if filepath.stat().st_size < 1_000_000:  # skip huge files
                    total_lines += sum(
                        1 for _ in filepath.open("r", encoding="utf-8", errors="ignore")
                    )
            except (OSError, UnicodeDecodeError):
                pass

    # Detect frameworks from file content (sample a few files)
    frameworks = detect_frameworks(root)

    # Determine dominant language
    sorted_langs = sorted(languages.items(), key=lambda x: x[1], reverse=True)

    return RepositoryMetadata(
        name=root.name,
        root_path=str(root),
        languages=[lang for lang, _ in sorted_langs],
        frameworks=frameworks,
        build_systems=build_systems,
        total_files=total_files,
        total_lines=total_lines,
    )


def detect_frameworks(root: Path) -> list[str]:
    """Detect frameworks by sampling a small number of files."""
    frameworks: list[str] = []
    sample_count = 0
    max_samples = 50

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in SKIP_DIRS
        ]
        for filename in filenames:
            if sample_count >= max_samples:
                return frameworks

            ext = Path(filename).suffix.lower()
            if ext not in {".py", ".js", ".ts", ".go", ".rs", ".java", ".kt"}:
                continue

            filepath = Path(dirpath) / filename
            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")[:4096]
                content_lower = content.lower()
                for framework, markers in FRAMEWORK_MARKERS.items():
                    if any(m in content_lower for m in markers) and framework not in frameworks:
                        frameworks.append(framework)
            except OSError:
                pass

            sample_count += 1

    return frameworks


def get_language_for_file(file_path: str | Path) -> str:
    """Return the language for a single file based on its extension."""
    ext = Path(file_path).suffix.lower()
    return EXTENSION_MAP.get(ext, "unknown")
