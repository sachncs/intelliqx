from __future__ import annotations

from itertools import pairwise
from typing import ClassVar

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from intelliqx_graph.models import ComplexityEstimate, GraphLayer
from intelliqx_graph.query import GraphIndex

MAX_ENTRY_POINTS: int = 10
MAX_EXIT_POINTS: int = 10
MAX_CRITICAL_PATHS: int = 20
MIN_CACHE_FAN_IN: int = 3
HIGH_CACHE_FAN_IN: int = 5
HIGH_CACHE_SPEEDUP_FAN_IN: int = 8
MIN_PARALLEL_SUCCESSORS: int = 3
FAN_IN_COST_WEIGHT: float = 0.1
DEFAULT_EDGE_WEIGHT: float = 1.0


class CriticalPathInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    path: list[str]
    path_length: int
    total_weight: float


class ExpensiveComputation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_name: str
    complexity: str
    fan_in: int
    fan_out: int
    callers: list[str] = Field(default_factory=list)
    cost_score: float = 0.0


class CachingOpportunity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_name: str
    reason: str
    estimated_speedup: str
    fan_in: int


class ParallelizationOpportunity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_ids: list[str]
    reason: str
    potential_speedup: str


class PerformanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    critical_paths: list[CriticalPathInfo] = Field(default_factory=list)
    expensive_computations: list[ExpensiveComputation] = Field(default_factory=list)
    caching_opportunities: list[CachingOpportunity] = Field(default_factory=list)
    parallelization_opportunities: list[ParallelizationOpportunity] = Field(default_factory=list)
    total_nodes_analyzed: int = 0
    high_complexity_nodes: int = 0
    average_complexity_distribution: dict[str, int] = Field(default_factory=dict)


class PerformanceAgent:
    EXPENSIVE_COMPLEXITIES: ClassVar[set[str]] = {
        ComplexityEstimate.QUADRATIC.value,
        ComplexityEstimate.CUBIC.value,
        ComplexityEstimate.EXPONENTIAL.value,
    }
    COMPLEXITY_COSTS: ClassVar[dict[str, float]] = {
        "O(2^n)": 100.0,
        "O(n^3)": 50.0,
        "O(n^2)": 20.0,
        "O(n log n)": 3.0,
        "O(n)": 1.0,
        "O(log n)": 0.5,
        "O(1)": 0.1,
    }

    def __init__(self, graph_index: GraphIndex) -> None:
        self.index = graph_index

    def analyze(self) -> PerformanceReport:
        call_graph = self.index.get_graph(GraphLayer.CALL)
        if call_graph is None:
            return PerformanceReport()

        critical_paths = self.find_critical_paths(call_graph)
        expensive = self.find_expensive_computations(call_graph)
        caching = self.find_caching_opportunities(call_graph)
        parallelization = self.find_parallelization_opportunities(call_graph)
        complexity_dist = self.complexity_distribution(call_graph)
        high_complexity = sum(
            count
            for complexity, count in complexity_dist.items()
            if complexity in self.EXPENSIVE_COMPLEXITIES
        )

        return PerformanceReport(
            critical_paths=critical_paths,
            expensive_computations=expensive,
            caching_opportunities=caching,
            parallelization_opportunities=parallelization,
            total_nodes_analyzed=call_graph.number_of_nodes(),
            high_complexity_nodes=high_complexity,
            average_complexity_distribution=complexity_dist,
        )

    def find_critical_paths(self, call_graph: nx.DiGraph) -> list[CriticalPathInfo]:
        entry_points = [n for n in call_graph.nodes if call_graph.in_degree(n) == 0]
        if not entry_points:
            return []

        exit_points = [n for n in call_graph.nodes if call_graph.out_degree(n) == 0]

        paths: list[CriticalPathInfo] = []
        for source in entry_points[:MAX_ENTRY_POINTS]:
            for target in exit_points[:MAX_EXIT_POINTS]:
                if source == target:
                    continue
                path = self.index.critical_path(source, target, layer=GraphLayer.CALL)
                if path is None or len(path) < 2:
                    continue

                weight = sum(
                    call_graph[u][v].get("weight", DEFAULT_EDGE_WEIGHT) for u, v in pairwise(path)
                )
                paths.append(
                    CriticalPathInfo(
                        source=source,
                        target=target,
                        path=path,
                        path_length=len(path),
                        total_weight=weight,
                    )
                )

        paths.sort(key=lambda p: p.total_weight, reverse=True)
        return paths[:MAX_CRITICAL_PATHS]

    def find_expensive_computations(self, call_graph: nx.DiGraph) -> list[ExpensiveComputation]:
        expensive: list[ExpensiveComputation] = []
        sg = self.index.software_graph

        for node_id in call_graph.nodes:
            node = sg.find_node(node_id)
            if node is None:
                continue

            if node.complexity.value not in self.EXPENSIVE_COMPLEXITIES:
                continue

            fi = self.index.fan_in(node_id, layer=GraphLayer.CALL)
            fo = self.index.fan_out(node_id, layer=GraphLayer.CALL)

            callers = list(call_graph.predecessors(node_id))

            cost_score = self.COMPLEXITY_COSTS.get(node.complexity.value, 1.0) * (
                1 + fi * FAN_IN_COST_WEIGHT
            )

            expensive.append(
                ExpensiveComputation(
                    node_id=node_id,
                    node_name=node.name,
                    complexity=node.complexity.value,
                    fan_in=fi,
                    fan_out=fo,
                    callers=callers,
                    cost_score=cost_score,
                )
            )

        expensive.sort(key=lambda e: e.cost_score, reverse=True)
        return expensive

    def find_caching_opportunities(self, call_graph: nx.DiGraph) -> list[CachingOpportunity]:
        opportunities: list[CachingOpportunity] = []
        sg = self.index.software_graph

        for node_id in call_graph.nodes:
            fi = self.index.fan_in(node_id, layer=GraphLayer.CALL)
            if fi < MIN_CACHE_FAN_IN:
                continue

            node = sg.find_node(node_id)
            if node is None:
                continue

            has_side_effects = len(node.side_effects) > 0
            is_pure = not has_side_effects and not node.failure_modes

            if is_pure and fi >= MIN_CACHE_FAN_IN:
                estimated = "moderate" if fi < HIGH_CACHE_SPEEDUP_FAN_IN else "significant"
                opportunities.append(
                    CachingOpportunity(
                        node_id=node_id,
                        node_name=node.name,
                        reason=f"Pure function called {fi} times with no side effects",
                        estimated_speedup=f"{estimated} speedup by caching results",
                        fan_in=fi,
                    )
                )
            elif fi >= HIGH_CACHE_FAN_IN:
                opportunities.append(
                    CachingOpportunity(
                        node_id=node_id,
                        node_name=node.name,
                        reason=f"High fan-in ({fi} callers); consider memoizing if inputs are bounded",
                        estimated_speedup="variable depending on input distribution",
                        fan_in=fi,
                    )
                )

        opportunities.sort(key=lambda o: o.fan_in, reverse=True)
        return opportunities

    def find_parallelization_opportunities(
        self, call_graph: nx.DiGraph
    ) -> list[ParallelizationOpportunity]:
        opportunities: list[ParallelizationOpportunity] = []

        for node_id in call_graph.nodes:
            successors = list(call_graph.successors(node_id))
            if len(successors) < MIN_PARALLEL_SUCCESSORS:
                continue

            independent = []
            for s in successors:
                has_cross_dep = any(
                    other != s and nx.has_path(call_graph, s, other) for other in successors
                )
                if not has_cross_dep:
                    independent.append(s)

            if len(independent) >= MIN_PARALLEL_SUCCESSORS:
                opportunities.append(
                    ParallelizationOpportunity(
                        node_ids=[node_id] + independent,
                        reason=f"Node {node_id} fans out to {len(independent)} independent successors",
                        potential_speedup=f"Up to {len(independent)}x parallelism",
                    )
                )

        return opportunities

    def complexity_distribution(self, call_graph: nx.DiGraph) -> dict[str, int]:
        dist: dict[str, int] = {}
        sg = self.index.software_graph

        for node_id in call_graph.nodes:
            node = sg.find_node(node_id)
            complexity = node.complexity.value if node else "unknown"
            dist[complexity] = dist.get(complexity, 0) + 1

        return dist
