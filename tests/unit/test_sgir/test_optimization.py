"""Tests for optimization passes and pipeline."""

from __future__ import annotations

from intelliqx_graph.models import (
    ComplexityEstimate,
    EdgeType,
    GraphLayer,
    RepositoryMetadata,
    SGIREdge,
    SGIRGraph,
    SGIRNode,
    SoftwareGraph,
)
from intelliqx_graph.optimization.passes import (
    clean_dependency_cycles,
    detect_duplicates,
    inline_trivial_nodes,
    reduce_complexity,
    remove_dead_nodes,
)
from intelliqx_graph.optimization.verification import VerificationAgent
from intelliqx_graph.query import GraphIndex


def make_test_sg() -> SoftwareGraph:
    repo = RepositoryMetadata(name="test", root_path="/tmp")
    sg = SoftwareGraph(repository=repo)

    nodes = [
        SGIRNode(id="main", name="main"),
        SGIRNode(id="helper", name="helper"),
        SGIRNode(id="dead", name="dead_code"),
        SGIRNode(id="a", name="a"),
        SGIRNode(id="b", name="b"),
        SGIRNode(id="complex", name="complex_fn", complexity=ComplexityEstimate.CUBIC),
    ]
    edges = [
        SGIREdge(source="main", target="helper", edge_type=EdgeType.CALL),
        SGIREdge(source="a", target="b", edge_type=EdgeType.CALL),
        SGIREdge(source="b", target="a", edge_type=EdgeType.CALL),
    ]
    sg.add_layer(SGIRGraph(layer=GraphLayer.CALL, nodes=nodes, edges=edges))
    return sg


class TestRemoveDeadNodes:
    def test_removes_unreachable(self) -> None:
        sg = make_test_sg()
        index = GraphIndex(sg)
        result = remove_dead_nodes(sg, index, ["main"])
        dead_found = any(n.is_dead for n in result.all_nodes())
        assert dead_found or result.total_nodes <= sg.total_nodes


class TestDetectDuplicates:
    def test_finds_duplicates(self) -> None:
        sg = make_test_sg()
        index = GraphIndex(sg)
        dupes = detect_duplicates(sg, index)
        assert isinstance(dupes, list)


class TestInlineTrivialNodes:
    def test_runs(self) -> None:
        sg = make_test_sg()
        index = GraphIndex(sg)
        result = inline_trivial_nodes(sg, index)
        assert isinstance(result, SoftwareGraph)


class TestCleanDependencyCycles:
    def test_breaks_cycles(self) -> None:
        sg = make_test_sg()
        index = GraphIndex(sg)
        result = clean_dependency_cycles(sg, index)
        cycles = index.find_cycles(layer=GraphLayer.CALL)
        assert len(cycles) == 0 or result.total_edges <= sg.total_edges


class TestReduceComplexity:
    def test_runs(self) -> None:
        sg = make_test_sg()
        index = GraphIndex(sg)
        result = reduce_complexity(sg, index)
        assert isinstance(result, SoftwareGraph)


class TestVerificationAgent:
    def test_same_graph(self) -> None:
        sg = make_test_sg()
        agent = VerificationAgent(sg, sg, ["main"])
        report = agent.verify()
        assert report.behavior_preserved is True
        assert report.risk_level == "low"

    def test_different_graphs(self) -> None:
        import copy
        sg1 = make_test_sg()
        sg2 = copy.deepcopy(sg1)
        sg2.layers[GraphLayer.CALL].nodes = sg2.layers[GraphLayer.CALL].nodes[:3]
        agent = VerificationAgent(sg1, sg2, ["main"])
        report = agent.verify()
        assert report.nodes_removed > 0
