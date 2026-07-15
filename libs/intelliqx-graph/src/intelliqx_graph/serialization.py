"""SGIR serialization — JSON and Parquet persistence.

Provides helpers to persist and load a ``SoftwareGraph`` to/from
JSON files and Parquet tables (backed by the existing intelliqx-kg
Parquet+DuckDB infrastructure).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from intelliqx_graph.models import (
    SGIRNode,
    SoftwareGraph,
)


def graph_to_json(sg: SoftwareGraph) -> str:
    """Serialize a ``SoftwareGraph`` to a JSON string."""
    return sg.model_dump_json(indent=2)


def graph_from_json(raw: str) -> SoftwareGraph:
    """Deserialize a ``SoftwareGraph`` from a JSON string."""
    return SoftwareGraph.model_validate_json(raw)


def graph_to_file(sg: SoftwareGraph, path: Path) -> None:
    """Write a ``SoftwareGraph`` to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(graph_to_json(sg), encoding="utf-8")


def graph_from_file(path: Path) -> SoftwareGraph:
    """Read a ``SoftwareGraph`` from a JSON file."""
    return graph_from_json(path.read_text(encoding="utf-8"))


def graph_to_dict(sg: SoftwareGraph) -> dict[str, Any]:
    """Serialize a ``SoftwareGraph`` to a plain dict."""
    return sg.model_dump(mode="json")


def graph_from_dict(data: dict[str, Any]) -> SoftwareGraph:
    """Deserialize a ``SoftwareGraph`` from a plain dict."""
    return SoftwareGraph.model_validate(data)


def nodes_to_parquet(nodes: list[SGIRNode], path: Path) -> None:
    """Write SGIR nodes to a Parquet file.

    Requires ``pyarrow`` to be installed. Falls back to JSON if
    pyarrow is unavailable.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        records = [n.model_dump(mode="json") for n in nodes]
        table = pa.table({}) if not records else pa.Table.from_pylist(records)
        pq.write_table(table, path)
    except ImportError:
        # Fallback: write as JSON lines
        path.write_text(
            "\n".join(json.dumps(n.model_dump(mode="json")) for n in nodes),
            encoding="utf-8",
        )


def nodes_from_parquet(path: Path) -> list[SGIRNode]:
    """Read SGIR nodes from a Parquet or JSON-lines file."""
    try:
        import pyarrow.parquet as pq

        table = pq.read_table(path)
        return [SGIRNode.model_validate(row) for row in table.to_pylist()]
    except ImportError:
        nodes: list[SGIRNode] = []
        for line in path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                nodes.append(SGIRNode.model_validate_json(line))
        return nodes
