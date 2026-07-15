"""Tests for serialization module."""

from __future__ import annotations

from pathlib import Path

from intelliqx_graph.models import (
    GraphLayer,
    RepositoryMetadata,
    SGIRGraph,
    SGIRNode,
    SoftwareGraph,
)
from intelliqx_graph.serialization import (
    graph_from_dict,
    graph_from_file,
    graph_from_json,
    graph_to_dict,
    graph_to_file,
    graph_to_json,
)


def _make_test_sg() -> SoftwareGraph:
    repo = RepositoryMetadata(name="test", root_path="/tmp")
    sg = SoftwareGraph(repository=repo)
    sg.add_layer(SGIRGraph(
        layer=GraphLayer.CALL,
        nodes=[SGIRNode(id="n1", name="main")],
    ))
    return sg


class TestSerialization:
    def test_roundtrip_json(self) -> None:
        sg = _make_test_sg()
        raw = graph_to_json(sg)
        sg2 = graph_from_json(raw)
        assert sg2.repository.name == "test"
        assert sg2.total_nodes == 1

    def test_roundtrip_dict(self) -> None:
        sg = _make_test_sg()
        d = graph_to_dict(sg)
        sg2 = graph_from_dict(d)
        assert sg2.total_nodes == 1

    def test_roundtrip_file(self, tmp_path: Path) -> None:
        sg = _make_test_sg()
        path = tmp_path / "sg.json"
        graph_to_file(sg, path)
        sg2 = graph_from_file(path)
        assert sg2.repository.name == "test"
