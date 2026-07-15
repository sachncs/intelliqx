"""Tests for graph query/index and networkx operations."""

from __future__ import annotations

import networkx as nx
from intelliqx_graph.models import (
    EdgeType,
    GraphLayer,
    RepositoryMetadata,
    SGIREdge,
    SGIRGraph,
    SGIRNode,
    SoftwareGraph,
)
from intelliqx_graph.query import GraphIndex


def _build_test_sg() -> SoftwareGraph:
    repo = RepositoryMetadata(name="test", root_path="/tmp")
    sg = SoftwareGraph(repository=repo)

    nodes = [
        SGIRNode(id="entry", name="main", purpose="entry point"),
        SGIRNode(id="auth", name="authenticate", purpose="auth"),
        SGIRNode(id="db", name="query_db", purpose="database"),
        SGIRNode(id="render", name="render", purpose="output"),
        SGIRNode(id="dead", name="unused", purpose="dead code"),
    ]
    edges = [
        SGIREdge(source="entry", target="auth", edge_type=EdgeType.CALL),
        SGIREdge(source="auth", target="db", edge_type=EdgeType.CALL),
        SGIREdge(source="db", target="render", edge_type=EdgeType.DATA),
    ]
    sg.add_layer(SGIRGraph(layer=GraphLayer.CALL, nodes=nodes, edges=edges))
    return sg


class TestGraphIndex:
    def test_build(self) -> None:
        sg = _build_test_sg()
        index = GraphIndex(sg)
        assert index.all_node_ids() == {"entry", "auth", "db", "render", "dead"}

    def test_reachable_from(self) -> None:
        sg = _build_test_sg()
        index = GraphIndex(sg)
        reachable = index.reachable_from("entry")
        assert "auth" in reachable
        assert "db" in reachable
        assert "render" in reachable
        assert "dead" not in reachable

    def test_can_reach(self) -> None:
        sg = _build_test_sg()
        index = GraphIndex(sg)
        assert index.can_reach("entry", "render")
        assert not index.can_reach("render", "entry")

    def test_dead_nodes(self) -> None:
        sg = _build_test_sg()
        index = GraphIndex(sg)
        dead = index.find_dead_nodes(["entry"])
        assert "dead" in dead
        assert "entry" not in dead
        assert "auth" not in dead

    def test_fan_in_fan_out(self) -> None:
        sg = _build_test_sg()
        index = GraphIndex(sg)
        assert index.fan_out("entry") == 1
        assert index.fan_in("auth") == 1
        assert index.fan_in("entry") == 0

    def test_topological_order(self) -> None:
        sg = _build_test_sg()
        index = GraphIndex(sg)
        order = index.topological_order()
        assert order is not None
        assert order.index("entry") < order.index("auth")
        assert order.index("auth") < order.index("db")

    def test_detect_communities(self) -> None:
        sg = _build_test_sg()
        index = GraphIndex(sg)
        communities = index.detect_communities()
        assert len(communities) > 0

    def test_find_cycles_acyclic(self) -> None:
        sg = _build_test_sg()
        index = GraphIndex(sg)
        cycles = index.find_cycles()
        assert len(cycles) == 0

    def test_find_cycles_cyclic(self) -> None:
        repo = RepositoryMetadata(name="test", root_path="/tmp")
        sg = SoftwareGraph(repository=repo)
        nodes = [
            SGIRNode(id="a", name="a"),
            SGIRNode(id="b", name="b"),
        ]
        edges = [
            SGIREdge(source="a", target="b", edge_type=EdgeType.CALL),
            SGIREdge(source="b", target="a", edge_type=EdgeType.CALL),
        ]
        sg.add_layer(SGIRGraph(layer=GraphLayer.CALL, nodes=nodes, edges=edges))
        index = GraphIndex(sg)
        cycles = index.find_cycles()
        assert len(cycles) > 0

    def test_stats(self) -> None:
        sg = _build_test_sg()
        index = GraphIndex(sg)
        stats = index.stats()
        assert stats["total_layers"] == 1
        assert "call" in stats["layers"]
        assert stats["layers"]["call"]["nodes"] == 5

    def test_critical_path(self) -> None:
        sg = _build_test_sg()
        index = GraphIndex(sg)
        path = index.critical_path("entry", "render")
        assert path is not None
        assert path[0] == "entry"
        assert path[-1] == "render"

    def test_subgraph_isomorphism(self) -> None:
        sg = _build_test_sg()
        index = GraphIndex(sg)

        pattern = nx.DiGraph()
        pattern.add_edge("x", "y")

        mappings = index.find_subgraph_isomorphisms(pattern)
        assert len(mappings) > 0
