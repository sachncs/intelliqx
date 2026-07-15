from __future__ import annotations

from itertools import pairwise

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from intelliqx_graph.models import GraphLayer
from intelliqx_graph.query import GraphIndex


class ExecutionPath(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: list[str]
    length: int
    total_weight: float


class DeadCodeNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_name: str
    node_type: str
    language: str
    source_file: str | None = None


class BottleneckNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_name: str
    fan_in: int
    fan_out: int
    bottleneck_score: float
    impact: str


class FlowAnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_points: list[str] = Field(default_factory=list)
    execution_paths: list[ExecutionPath] = Field(default_factory=list)
    longest_path_length: int = 0
    dead_code: list[DeadCodeNode] = Field(default_factory=list)
    bottlenecks: list[BottleneckNode] = Field(default_factory=list)
    unreachable_from_any_entry: list[str] = Field(default_factory=list)
    total_reachable: int = 0
    total_unreachable: int = 0
    graph_is_dag: bool = True
    strongly_connected_components: int = 0


class FlowAnalysisAgent:
    def __init__(self, graph_index: GraphIndex) -> None:
        self.index = graph_index

    def analyze(self) -> FlowAnalysisReport:
        call_graph = self.index.get_graph(GraphLayer.CALL)
        if call_graph is None:
            return FlowAnalysisReport()

        entry_points = self.find_entry_points(call_graph)
        execution_paths = self.find_execution_paths(call_graph, entry_points)
        dead_code = self.find_dead_code(entry_points)
        bottlenecks = self.find_bottlenecks(call_graph)
        unreachable = self.index.find_dead_nodes(entry_points, layer=GraphLayer.CALL)

        reachable: set[str] = set()
        for ep in entry_points:
            if ep in call_graph:
                reachable.update(self.index.reachable_from(ep, layer=GraphLayer.CALL))
                reachable.add(ep)

        longest = max((len(p.path) for p in execution_paths), default=0)
        stats = self.index.stats()
        call_stats = stats["layers"].get("call", {})

        return FlowAnalysisReport(
            entry_points=entry_points,
            execution_paths=execution_paths,
            longest_path_length=longest,
            dead_code=dead_code,
            bottlenecks=bottlenecks,
            unreachable_from_any_entry=list(unreachable),
            total_reachable=len(reachable),
            total_unreachable=len(unreachable),
            graph_is_dag=call_stats.get("is_dag", True),
            strongly_connected_components=call_stats.get("num_strongly_connected", 0),
        )

    def find_entry_points(self, call_graph: nx.DiGraph) -> list[str]:
        entry_points = [n for n in call_graph.nodes if call_graph.in_degree(n) == 0]
        if not entry_points:
            sccs = list(nx.strongly_connected_components(call_graph))
            if sccs:
                largest_scc = max(sccs, key=len)
                entry_points = list(largest_scc)[:5]
        return entry_points

    def find_execution_paths(
        self, call_graph: nx.DiGraph, entry_points: list[str]
    ) -> list[ExecutionPath]:
        paths: list[ExecutionPath] = []
        for ep in entry_points:
            if ep not in call_graph:
                continue
            for target in nx.descendants(call_graph, ep):
                try:
                    path = nx.shortest_path(call_graph, ep, target)
                    weight = sum(
                        call_graph[u][v].get("weight", 1.0)
                        for u, v in pairwise(path)
                    )
                    paths.append(ExecutionPath(
                        path=path,
                        length=len(path),
                        total_weight=weight,
                    ))
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue

        paths.sort(key=lambda p: p.total_weight, reverse=True)
        return paths[:100]

    def find_dead_code(self, entry_points: list[str]) -> list[DeadCodeNode]:
        unreachable_ids = self.index.find_dead_nodes(entry_points, layer=GraphLayer.CALL)
        dead_nodes: list[DeadCodeNode] = []
        sg = self.index.software_graph
        for node_id in unreachable_ids:
            node = sg.find_node(node_id)
            if node is not None:
                dead_nodes.append(DeadCodeNode(
                    node_id=node.id,
                    node_name=node.name,
                    node_type=node.node_type.value,
                    language=node.language,
                    source_file=node.source_location.file_path if node.source_location else None,
                ))
            else:
                dead_nodes.append(DeadCodeNode(
                    node_id=node_id,
                    node_name=node_id,
                    node_type="unknown",
                    language="unknown",
                ))
        return dead_nodes

    def find_bottlenecks(self, call_graph: nx.DiGraph) -> list[BottleneckNode]:
        bottlenecks: list[BottleneckNode] = []
        for node_id in call_graph.nodes:
            fi = call_graph.in_degree(node_id)
            fo = call_graph.out_degree(node_id)
            score = fi + fo
            if score < 8:
                continue

            if fi > 10 and fo > 5:
                impact = "Critical: high fan-in and fan-out indicate a central hub"
            elif fi > 10:
                impact = "High fan-in: many components depend on this node"
            elif fo > 10:
                impact = "High fan-out: this node depends on many others"
            else:
                impact = "Moderate bottleneck"

            node_data = call_graph.nodes[node_id]
            node_name = node_data.get("name", node_id)

            bottlenecks.append(BottleneckNode(
                node_id=node_id,
                node_name=str(node_name),
                fan_in=fi,
                fan_out=fo,
                bottleneck_score=float(score),
                impact=impact,
            ))

        bottlenecks.sort(key=lambda b: b.bottleneck_score, reverse=True)
        return bottlenecks
