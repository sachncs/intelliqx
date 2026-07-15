"""Tests for analysis agents."""

from __future__ import annotations

from intelliqx_graph.analysis import (
    ArchitectureAgent,
    ArchitectureReport,
    FlowAnalysisAgent,
    FlowAnalysisReport,
    PerformanceAgent,
    PerformanceReport,
    SecurityAgent,
    SecurityReport,
)
from intelliqx_graph.models import (
    ComplexityEstimate,
    EdgeType,
    GraphLayer,
    RepositoryMetadata,
    SecurityBoundary,
    SGIREdge,
    SGIRGraph,
    SGIRNode,
    SoftwareGraph,
)
from intelliqx_graph.query import GraphIndex


def _make_test_sg() -> SoftwareGraph:
    repo = RepositoryMetadata(name="test", root_path="/tmp")
    sg = SoftwareGraph(repository=repo)

    nodes = [
        SGIRNode(id="main", name="main", purpose="entry"),
        SGIRNode(id="auth", name="authenticate", purpose="auth", complexity=ComplexityEstimate.QUADRATIC),
        SGIRNode(id="db", name="query_db", purpose="database"),
        SGIRNode(id="render", name="render", purpose="output"),
        SGIRNode(id="admin", name="admin_fn", purpose="admin", security_boundary=SecurityBoundary.ADMIN),
    ]
    edges = [
        SGIREdge(source="main", target="auth", edge_type=EdgeType.CALL),
        SGIREdge(source="auth", target="db", edge_type=EdgeType.CALL),
        SGIREdge(source="db", target="render", edge_type=EdgeType.DATA),
        SGIREdge(source="main", target="admin", edge_type=EdgeType.CALL),
    ]
    sg.add_layer(SGIRGraph(layer=GraphLayer.CALL, nodes=nodes, edges=edges))
    sg.add_layer(SGIRGraph(layer=GraphLayer.DATA_FLOW, nodes=nodes, edges=edges))
    return sg


class TestArchitectureAgent:
    def test_analyze(self) -> None:
        sg = _make_test_sg()
        index = GraphIndex(sg)
        agent = ArchitectureAgent(index)
        report = agent.analyze()
        assert isinstance(report, ArchitectureReport)
        assert report.total_nodes > 0


class TestFlowAnalysisAgent:
    def test_analyze(self) -> None:
        sg = _make_test_sg()
        index = GraphIndex(sg)
        agent = FlowAnalysisAgent(index)
        report = agent.analyze()
        assert isinstance(report, FlowAnalysisReport)


class TestPerformanceAgent:
    def test_analyze(self) -> None:
        sg = _make_test_sg()
        index = GraphIndex(sg)
        agent = PerformanceAgent(index)
        report = agent.analyze()
        assert isinstance(report, PerformanceReport)


class TestSecurityAgent:
    def test_analyze(self) -> None:
        sg = _make_test_sg()
        index = GraphIndex(sg)
        agent = SecurityAgent(index)
        report = agent.analyze()
        assert isinstance(report, SecurityReport)
