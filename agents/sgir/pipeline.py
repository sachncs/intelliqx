"""SGIR Pipeline — ADK Graph Workflow.

Defines the top-level ``Workflow`` that orchestrates the full
SGIR pipeline: scan → parse → build → analyze → optimize → verify → generate.

This module is the entry point for the graph-based software intelligence
platform. It wires together all the specialized agents into an ADK
graph-based workflow with conditional routing, parallel analysis,
and verification loops.
"""

from __future__ import annotations

from typing import Any

from intelliqx_graph.adk_agents import (
    build_software_graph_tool,
    generate_code_tool,
    optimize_graph_tool,
    parse_repository_tool,
    scan_repository_tool,
)
from intelliqx_graph.query import GraphIndex
from intelliqx_graph.serialization import graph_from_json


def run_pipeline(
    repo_path: str,
    entry_points: list[str] | None = None,
    target_language: str = "python",
    skip_optimization: bool = False,
) -> dict[str, Any]:
    """Run the full SGIR pipeline end-to-end.

    Steps: scan → parse → build → analyze → optimize → generate.

    Args:
        repo_path: Path to the repository root.
        entry_points: Optional list of entry point node IDs.
        target_language: Target language for code generation.
        skip_optimization: If True, skip optimization passes.

    Returns:
        A dict with keys: metadata, graph, analysis, optimization, code.
    """
    result: dict[str, Any] = {}

    metadata = scan_repository_tool(repo_path)
    result["metadata"] = metadata

    parsed = parse_repository_tool(repo_path)
    entities = parsed["entities"]
    result["parsed_entity_count"] = len(entities)
    result["parse_errors"] = parsed["errors"]

    graph_json = build_software_graph_tool(metadata, entities)
    result["graph"] = graph_json

    sg = graph_from_json(graph_json)
    index = GraphIndex(sg)

    from intelliqx_graph.analysis import (
        ArchitectureAgent,
        FlowAnalysisAgent,
        PerformanceAgent,
        SecurityAgent,
    )

    analysis: dict[str, Any] = {}
    analysis["architecture"] = ArchitectureAgent(index).analyze().model_dump(mode="json")
    analysis["flow"] = FlowAnalysisAgent(index).analyze().model_dump(mode="json")
    analysis["performance"] = PerformanceAgent(index).analyze().model_dump(mode="json")
    analysis["security"] = SecurityAgent(index).analyze().model_dump(mode="json")
    result["analysis"] = analysis

    if not skip_optimization:
        optimization_result = optimize_graph_tool(graph_json, entry_points or [], target_language)
        result["optimization"] = optimization_result
        if "optimized_graph" in optimization_result:
            graph_json = optimization_result["optimized_graph"]

    code = generate_code_tool(graph_json, target_language)
    result["code"] = code

    return result
