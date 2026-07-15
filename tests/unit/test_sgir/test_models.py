"""Tests for SGIR core models."""

from __future__ import annotations

import pytest
from intelliqx_graph.models import (
    ComplexityEstimate,
    EdgeType,
    GraphLayer,
    NodeType,
    RepositoryMetadata,
    SecurityBoundary,
    SGIREdge,
    SGIRGraph,
    SGIRNode,
    SoftwareGraph,
    SourceLocation,
)


class TestSGIRNode:
    def test_basic_creation(self) -> None:
        node = SGIRNode(id="n1", name="process_data")
        assert node.id == "n1"
        assert node.name == "process_data"
        assert node.node_type == NodeType.UNKNOWN
        assert node.language == "unknown"
        assert node.is_dead is False
        assert node.is_duplicate is False

    def test_full_creation(self) -> None:
        node = SGIRNode(
            id="n2",
            name="authenticate_user",
            purpose="Validate user credentials",
            node_type=NodeType.FUNCTION,
            language="python",
            source_location=SourceLocation(
                file_path="auth.py", line_start=10, line_end=25
            ),
            inputs=["username", "password"],
            outputs=["bool"],
            preconditions=["user_exists"],
            postconditions=["authenticated"],
            side_effects=["log_attempt"],
            external_dependencies=["bcrypt"],
            complexity=ComplexityEstimate.LINEAR,
            failure_modes=["invalid_credentials", "db_unavailable"],
            security_boundary=SecurityBoundary.AUTHENTICATED,
            test_coverage=0.85,
        )
        assert node.purpose == "Validate user credentials"
        assert node.security_boundary == SecurityBoundary.AUTHENTICATED
        assert node.test_coverage == 0.85

    def test_extra_forbid(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SGIRNode(id="n3", name="x", unknown_field="bad")


class TestSGIREdge:
    def test_basic_creation(self) -> None:
        edge = SGIREdge(source="n1", target="n2", edge_type=EdgeType.CALL)
        assert edge.source == "n1"
        assert edge.target == "n2"
        assert edge.weight == 1.0

    def test_with_metadata(self) -> None:
        edge = SGIREdge(
            source="n1",
            target="n2",
            edge_type=EdgeType.DATA,
            weight=2.5,
            label="user_data",
            metadata={"format": "json"},
        )
        assert edge.weight == 2.5
        assert edge.metadata["format"] == "json"


class TestSGIRGraph:
    def test_empty_graph(self) -> None:
        graph = SGIRGraph(layer=GraphLayer.CALL)
        assert graph.node_count == 0
        assert graph.edge_count == 0
        assert graph.node_ids == set()

    def test_graph_with_nodes(self) -> None:
        nodes = [
            SGIRNode(id="n1", name="a"),
            SGIRNode(id="n2", name="b"),
            SGIRNode(id="n3", name="c"),
        ]
        edges = [
            SGIREdge(source="n1", target="n2", edge_type=EdgeType.CALL),
            SGIREdge(source="n2", target="n3", edge_type=EdgeType.CALL),
        ]
        graph = SGIRGraph(layer=GraphLayer.CALL, nodes=nodes, edges=edges)
        assert graph.node_count == 3
        assert graph.edge_count == 2
        assert graph.node_ids == {"n1", "n2", "n3"}


class TestSoftwareGraph:
    def _make_sg(self) -> SoftwareGraph:
        repo = RepositoryMetadata(name="test", root_path="/tmp/test")
        sg = SoftwareGraph(repository=repo)
        nodes = [SGIRNode(id="n1", name="main")]
        sg.add_layer(SGIRGraph(layer=GraphLayer.CALL, nodes=nodes))
        return sg

    def test_add_and_get_layer(self) -> None:
        sg = self._make_sg()
        assert sg.get_layer(GraphLayer.CALL) is not None
        assert sg.get_layer(GraphLayer.DATA_FLOW) is None

    def test_total_nodes(self) -> None:
        sg = self._make_sg()
        sg.add_layer(SGIRGraph(
            layer=GraphLayer.DATA_FLOW,
            nodes=[SGIRNode(id="d1", name="x"), SGIRNode(id="d2", name="y")],
        ))
        assert sg.total_nodes == 3

    def test_find_node(self) -> None:
        sg = self._make_sg()
        found = sg.find_node("n1")
        assert found is not None
        assert found.name == "main"
        assert sg.find_node("nonexistent") is None

    def test_layers_present(self) -> None:
        sg = self._make_sg()
        assert GraphLayer.CALL in sg.layers_present
        assert GraphLayer.SECURITY not in sg.layers_present

    def test_all_nodes(self) -> None:
        sg = self._make_sg()
        all_nodes = sg.all_nodes()
        assert len(all_nodes) == 1
