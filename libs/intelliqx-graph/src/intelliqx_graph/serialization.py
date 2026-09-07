"""SGIR JSON serialization.

Provides helpers to persist and load a ``SoftwareGraph``
to/from JSON strings and files. JSON is the single
serialized wire format for ``SoftwareGraph``; the previous
Parquet round-trip fell out of use after the graph
became Python-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from intelliqx_graph.models import SoftwareGraph


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
