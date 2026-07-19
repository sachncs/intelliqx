"""SGIR Pipeline — top-level workflow.

Orchestrates the full SGIR pipeline: scan → parse → build →
optimize → generate. The same steps run end-to-end against
a repository root and return a structured dict with the
metadata, parsed entities, generated graph, optimization
result, and generated code.
"""

from __future__ import annotations

from typing import Any

from intelliqx_graph.operations import (
    build_software_graph,
    generate_code,
    optimize_graph,
    parse_repository,
    scan_repository,
)


def run_pipeline(
    repo_path: str,
    entry_points: list[str] | None = None,
    target_language: str = "python",
    skip_optimization: bool = False,
) -> dict[str, Any]:
    """Run the full SGIR pipeline end-to-end.

    Steps: scan → parse → build → optimize → generate.
    """
    result: dict[str, Any] = {}

    metadata = scan_repository(repo_path)
    result["metadata"] = metadata

    parsed = parse_repository(repo_path)
    entities = parsed["entities"]
    result["parsed_entity_count"] = len(entities)
    result["parse_errors"] = parsed["errors"]

    graph_json = build_software_graph(metadata, entities)
    result["graph"] = graph_json

    if not skip_optimization:
        optimization_result = optimize_graph(graph_json, entry_points or [], target_language)
        result["optimization"] = optimization_result

    code = generate_code(graph_json, target_language)
    result["code"] = code

    return result
