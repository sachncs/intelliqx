"""ADK agent wrappers for SGIR pipeline.

Wraps the existing ``intelliqx-core`` and ``intelliqx-graph`` components
as ADK ``Agent`` instances for use in graph-based workflows.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from intelliqx_graph.analysis import (
    ArchitectureAgent,
    FlowAnalysisAgent,
    PerformanceAgent,
    SecurityAgent,
)
from intelliqx_graph.backends import get_backend
from intelliqx_graph.models import SoftwareGraph
from intelliqx_graph.optimization import OptimizationPipeline
from intelliqx_graph.parsers import ParsedEntity
from intelliqx_graph.parsers.python_parser import PythonParser
from intelliqx_graph.query import GraphIndex
from intelliqx_graph.repository import scan_repository
from intelliqx_graph.serialization import graph_from_json, graph_to_json

# ---------------------------------------------------------------------------
# Input/Output models for ADK tools
# ---------------------------------------------------------------------------


class RepositoryInput(BaseModel):
    """Input for repository analysis."""

    model_config = ConfigDict(extra="forbid")

    repo_path: str


class GraphBuildInput(BaseModel):
    """Input for graph construction."""

    model_config = ConfigDict(extra="forbid")

    repository_metadata: dict[str, Any]
    parsed_entities: list[dict[str, Any]]


class AnalysisInput(BaseModel):
    """Input for graph analysis."""

    model_config = ConfigDict(extra="forbid")

    software_graph_json: str


class OptimizationInput(BaseModel):
    """Input for optimization."""

    model_config = ConfigDict(extra="forbid")

    software_graph_json: str
    entry_points: list[str] = Field(default_factory=list)
    target_language: str = "python"


class CodegenInput(BaseModel):
    """Input for code generation."""

    model_config = ConfigDict(extra="forbid")

    software_graph_json: str
    target_language: str


# ---------------------------------------------------------------------------
# ADK Tool functions (plain functions callable by ADK agents)
# ---------------------------------------------------------------------------


def scan_repository_tool(repo_path: str) -> dict[str, Any]:
    """Scan a repository and return metadata.

    Detects languages, frameworks, build systems, and counts files.
    """
    metadata = scan_repository(repo_path)
    return metadata.model_dump(mode="json")


def parse_repository_tool(repo_path: str, languages: list[str] | None = None) -> list[dict[str, Any]]:
    """Parse repository files and return entities.

    Uses Python parser for .py files, tree-sitter for others,
    and regex fallback for unsupported languages.
    """
    from pathlib import Path

    root = Path(repo_path)
    if not root.is_dir():
        return []

    parsers_map: dict[str, Any] = {
        ".py": PythonParser(),
    }

    try:
        from intelliqx_graph.parsers.typescript_parser import TypeScriptParser
        ts_parser = TypeScriptParser()
        for ext in ts_parser.supported_extensions():
            parsers_map[ext] = ts_parser
    except ImportError:
        pass

    try:
        from intelliqx_graph.parsers.go_parser import GoParser
        go_parser = GoParser()
        for ext in go_parser.supported_extensions():
            parsers_map[ext] = go_parser
    except ImportError:
        pass

    try:
        from intelliqx_graph.parsers.java_parser import JavaParser
        java_parser = JavaParser()
        for ext in java_parser.supported_extensions():
            parsers_map[ext] = java_parser
    except ImportError:
        pass

    from intelliqx_graph.parsers.fallback_parser import FallbackParser
    fallback = FallbackParser()

    all_entities: list[ParsedEntity] = []
    skip_dirs = {".git", "__pycache__", "node_modules", "vendor", ".venv", "venv",
                 ".mypy_cache", ".pytest_cache", ".ruff_cache", "target", "dist", "build"}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for filename in filenames:
            fp = Path(dirpath) / filename
            ext = fp.suffix.lower()
            parser = parsers_map.get(ext, fallback)
            try:
                entities = parser.parse_file(fp)
                all_entities.extend(entities)
            except Exception:
                pass

    return [e.model_dump(mode="json") for e in all_entities]


def build_software_graph_tool(
    repository_metadata: dict[str, Any],
    parsed_entities: list[dict[str, Any]],
) -> str:
    """Build a SoftwareGraph from parsed entities.

    Constructs all 8 graph layers and returns the serialized graph.
    """
    from intelliqx_graph.models import RepositoryMetadata, SGIRGraph

    repo = RepositoryMetadata.model_validate(repository_metadata)
    entities = [ParsedEntity.model_validate(e) for e in parsed_entities]

    parsed_data: dict[str, Any] = {
        "entities": [e.model_dump(mode="json") for e in entities],
        "repository": repository_metadata,
    }

    sg = SoftwareGraph(repository=repo)

    try:
        from intelliqx_graph.optimization.layers import create_default_registry
        registry = create_default_registry()
        layer_graphs = registry.build_all(parsed_data)
        for _layer, graph in layer_graphs.items():
            sg.add_layer(graph)
    except Exception:
        from intelliqx_graph.models import GraphLayer
        for layer in GraphLayer:
            sg.add_layer(SGIRGraph(layer=layer))

    return graph_to_json(sg)


def analyze_architecture_tool(software_graph_json: str) -> dict[str, Any]:
    """Analyze software architecture from the graph.

    Returns coupling analysis, layering violations, and community detection.
    """
    sg = graph_from_json(software_graph_json)
    index = GraphIndex(sg)
    agent = ArchitectureAgent(index)
    report = agent.analyze()
    return report.model_dump(mode="json")


def analyze_flow_tool(software_graph_json: str) -> dict[str, Any]:
    """Analyze execution flow from the graph.

    Returns execution paths, dead code, and bottleneck analysis.
    """
    sg = graph_from_json(software_graph_json)
    index = GraphIndex(sg)
    agent = FlowAnalysisAgent(index)
    report = agent.analyze()
    return report.model_dump(mode="json")


def analyze_performance_tool(software_graph_json: str) -> dict[str, Any]:
    """Analyze performance characteristics from the graph.

    Returns critical path, expensive computations, and optimization recommendations.
    """
    sg = graph_from_json(software_graph_json)
    index = GraphIndex(sg)
    agent = PerformanceAgent(index)
    report = agent.analyze()
    return report.model_dump(mode="json")


def analyze_security_tool(software_graph_json: str) -> dict[str, Any]:
    """Analyze security posture from the graph.

    Returns sensitive data flow, trust boundary crossings, and vulnerability analysis.
    """
    sg = graph_from_json(software_graph_json)
    index = GraphIndex(sg)
    agent = SecurityAgent(index)
    report = agent.analyze()
    return report.model_dump(mode="json")


def optimize_graph_tool(
    software_graph_json: str,
    entry_points: list[str] | None = None,
    target_language: str = "python",
) -> dict[str, Any]:
    """Optimize the software graph.

    Applies dead code removal, duplicate detection, trivial inlining,
    complexity reduction, and cycle cleaning. Each pass is verified.
    """
    sg = graph_from_json(software_graph_json)
    index = GraphIndex(sg)
    pipeline = OptimizationPipeline()
    result = pipeline.run(
        sg, index,
        entry_points=entry_points or [],
        target_language=target_language,
    )
    return result.model_dump(mode="json")


def generate_code_tool(
    software_graph_json: str,
    target_language: str = "python",
) -> dict[str, str]:
    """Generate source code from the optimized graph.

    Produces source files organized in the target language's
    idiomatic directory structure.
    """
    sg = graph_from_json(software_graph_json)
    backend = get_backend(target_language)
    if backend is None:
        return {"error": f"No backend available for {target_language}"}
    return backend.generate(sg)
