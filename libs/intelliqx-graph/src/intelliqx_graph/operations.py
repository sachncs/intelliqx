"""Top-level SGIR pipeline operations.

These are the public entry points the SGIR pipeline exposes:

* :func:`scan_repository` — repository metadata
* :func:`parse_repository` — parsed entities and per-file errors
* :func:`build_software_graph` — software graph from parsed entities
* :func:`optimize_graph` — optimization pass over a software graph
* :func:`generate_code` — code generation from a software graph
* :func:`ingest_graph` — write parsed entities into an OKF :class:`Index`

Plain callables that return JSON strings or dicts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from intelliqx_graph.backends import get_backend
from intelliqx_graph.models import RepositoryMetadata, SoftwareGraph
from intelliqx_graph.optimization import OptimizationPipeline
from intelliqx_graph.parsers import ParsedEntity
from intelliqx_graph.parsers.python_parser import PythonParser
from intelliqx_graph.query import GraphIndex
from intelliqx_graph.repository import collect_repository_metadata
from intelliqx_graph.serialization import graph_from_json, graph_to_json

PYTHON_DIRECTORIES_TO_SKIP: frozenset[str] = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        "vendor",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "target",
        "dist",
        "build",
    }
)


def scan_repository(repo_path: str) -> dict[str, Any]:
    """Scan a repository and return metadata as a JSON-friendly dict."""
    metadata = collect_repository_metadata(repo_path)
    return metadata.model_dump(mode="json")


def parse_repository(repo_path: str) -> dict[str, list[dict[str, Any]]]:
    """Parse Python files under ``repo_path`` and return entities and errors.

    ``SyntaxError`` and file-read errors are recorded in the
    ``errors`` list so callers can observe them. Non-Python
    files are skipped deterministically (only ``.py`` and
    ``.pyi`` are visited).
    """
    root = Path(repo_path)
    if not root.is_dir():
        return {"entities": [], "errors": [{"file": repo_path, "error": "not a directory"}]}

    parser = PythonParser()
    all_entities: list[ParsedEntity] = []
    all_errors: list[dict[str, str]] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PYTHON_DIRECTORIES_TO_SKIP]
        for filename in filenames:
            fp = Path(dirpath) / filename
            if fp.suffix.lower() not in {".py", ".pyi"}:
                continue
            try:
                all_entities.extend(parser.parse_file(fp))
            except Exception as exc:
                all_errors.append({"file": str(fp), "error": str(exc)})

    return {"entities": [e.model_dump(mode="json") for e in all_entities], "errors": all_errors}


def build_software_graph(
    repository_metadata: dict[str, Any], parsed_entities: list[dict[str, Any]]
) -> str:
    """Build and serialize a ``SoftwareGraph`` from parsed entities."""
    from intelliqx_graph.optimization.layers import create_default_registry

    repo = RepositoryMetadata.model_validate(repository_metadata)
    entities = [ParsedEntity.model_validate(e) for e in parsed_entities]
    parsed_data: dict[str, Any] = {"entities": entities, "repository": repo}

    sg = SoftwareGraph(repository=repo)
    for graph in create_default_registry().build_all(parsed_data).values():
        sg.add_layer(graph)
    return graph_to_json(sg)


def optimize_graph(
    software_graph_json: str, entry_points: list[str] | None = None, target_language: str = "python"
) -> dict[str, Any]:
    """Optimize the software graph and return the result as a JSON-friendly dict."""
    sg = graph_from_json(software_graph_json)
    pipeline = OptimizationPipeline(
        graph=sg,
        graph_index=GraphIndex(sg),
        entry_points=entry_points or [],
        target_language=target_language,
    )
    return pipeline.run().model_dump(mode="json")


def generate_code(software_graph_json: str, target_language: str = "python") -> dict[str, str]:
    """Generate source code from the optimized graph."""
    sg = graph_from_json(software_graph_json)
    backend = get_backend(target_language)
    return backend.generate(sg)


def ingest_graph(parsed_entities: list[dict[str, Any]], *, index: Any) -> int:
    """Project parsed entities into OKF concepts and write them to ``index``.

    Each :class:`ParsedEntity` becomes one :class:`OKFConcept` whose
    ``concept_id`` is the entity's ``graph::<file>::<kind>::<name>``
    (or its existing ``id`` if it already follows the OKF scheme)
    and whose body contains the entity's full source segment. The
    embedded vector enables hybrid FTS+vector retrieval through the
    same :class:`Index` that holds OKF knowledge.

    Args:
        parsed_entities: Output of :func:`parse_repository`.
        index: An open :class:`intelliqx_okf.index.Index` instance.

    Returns:
        Number of concepts successfully written.
    """
    from intelliqx_okf.concept import OKFConcept
    from intelliqx_okf.frontmatter import OKFFrontmatter

    written = 0
    for raw in parsed_entities:
        entity = ParsedEntity.model_validate(raw)
        frontmatter = OKFFrontmatter(
            type=f"code.{entity.entity_type}",
            title=entity.name,
            description=(f"{entity.entity_type} {entity.name} in {entity.file_path}"),
            tags=[
                tag for tag in (entity.file_path, entity.entity_type, entity.parent or "") if tag
            ],
            extra_fields={
                "source": "ast-graph",
                "file_path": entity.file_path,
                "line_start": entity.line_start,
                "line_end": entity.line_end,
                "parent": entity.parent or "",
                "language": entity.language,
                "is_async": entity.is_async,
                "is_generator": entity.is_generator,
            },
        )
        concept = OKFConcept(
            concept_id=f"code::{entity.file_path}::{entity.entity_type}::{entity.name}",
            frontmatter=frontmatter,
            body=(
                f"# {entity.name}\n\n"
                f"`{entity.entity_type}` declared in `{entity.file_path}` "
                f"at lines {entity.line_start}-{entity.line_end}.\n\n"
                f"```\n{entity.parameters}\n```"
            ),
        )
        index.write(concept)
        written += 1
    return written
