from __future__ import annotations

from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from intelliqx_graph.models import EdgeType, GraphLayer
from intelliqx_graph.query import GraphIndex


class CouplingSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CouplingFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_name: str
    fan_in: int
    fan_out: int
    total_coupling: int
    severity: CouplingSeverity
    recommendation: str


class LayeringViolation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    target_id: str
    source_layer: str
    target_layer: str
    edge_type: str
    description: str


class ModuleInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: int
    node_ids: set[str]
    node_count: int
    internal_edges: int
    external_edges: int
    cohesion: float


class ArchitectureReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_nodes: int
    total_edges: int
    density: float
    is_dag: bool
    coupling_findings: list[CouplingFinding] = Field(default_factory=list)
    layering_violations: list[LayeringViolation] = Field(default_factory=list)
    modules: list[ModuleInfo] = Field(default_factory=list)
    cycles: list[list[str]] = Field(default_factory=list)
    high_coupling_nodes: list[str] = Field(default_factory=list)
    orphan_nodes: list[str] = Field(default_factory=list)


class ArchitectureAgent:
    CRITICAL_THRESHOLD: ClassVar[int] = 20
    HIGH_THRESHOLD: ClassVar[int] = 12
    MEDIUM_THRESHOLD: ClassVar[int] = 7
    FAN_THRESHOLD: ClassVar[int] = 10

    def __init__(self, graph_index: GraphIndex) -> None:
        self.index = graph_index

    def analyze(self) -> ArchitectureReport:
        stats = self.index.stats()

        total_nodes = (
            sum(layer_stats["nodes"] for layer_stats in stats["layers"].values())
            if stats["layers"]
            else 0
        )
        total_edges = (
            sum(layer_stats["edges"] for layer_stats in stats["layers"].values())
            if stats["layers"]
            else 0
        )

        call_stats = stats["layers"].get("call", {})
        density = call_stats.get("density", 0.0)
        is_dag = call_stats.get("is_dag", True)

        coupling_findings = self.detect_coupling()
        layering_violations = self.detect_layering_violations()
        modules = self.detect_modules()
        cycles = self.index.find_cycles(layer=GraphLayer.CALL)
        high_coupling = self.find_high_coupling_nodes()
        orphans = self.find_orphan_nodes()

        return ArchitectureReport(
            total_nodes=total_nodes,
            total_edges=total_edges,
            density=density,
            is_dag=is_dag,
            coupling_findings=coupling_findings,
            layering_violations=layering_violations,
            modules=modules,
            cycles=cycles,
            high_coupling_nodes=high_coupling,
            orphan_nodes=orphans,
        )

    def detect_coupling(self) -> list[CouplingFinding]:
        findings: list[CouplingFinding] = []
        call_graph = self.index.get_graph(GraphLayer.CALL)
        if call_graph is None:
            return findings

        for node_id in call_graph.nodes:
            fan_in = self.index.fan_in(node_id, layer=GraphLayer.CALL)
            fan_out = self.index.fan_out(node_id, layer=GraphLayer.CALL)
            total = fan_in + fan_out

            if total < self.MEDIUM_THRESHOLD:
                continue

            severity = self.coupling_severity(fan_in, fan_out)
            recommendation = self.coupling_recommendation(fan_in, fan_out)
            node_data = call_graph.nodes[node_id]
            node_name = node_data.get("name", node_id)

            findings.append(
                CouplingFinding(
                    node_id=node_id,
                    node_name=str(node_name),
                    fan_in=fan_in,
                    fan_out=fan_out,
                    total_coupling=total,
                    severity=severity,
                    recommendation=recommendation,
                )
            )

        findings.sort(key=lambda f: f.total_coupling, reverse=True)
        return findings

    def coupling_severity(self, fan_in: int, fan_out: int) -> CouplingSeverity:
        total = fan_in + fan_out
        if total >= self.CRITICAL_THRESHOLD:
            return CouplingSeverity.CRITICAL
        if total >= self.HIGH_THRESHOLD:
            return CouplingSeverity.HIGH
        if total >= self.MEDIUM_THRESHOLD:
            return CouplingSeverity.MEDIUM
        return CouplingSeverity.LOW

    def coupling_recommendation(self, fan_in: int, fan_out: int) -> str:
        if fan_in > self.FAN_THRESHOLD:
            return "High fan-in suggests this node is a shared utility; consider extracting into a dedicated module"
        if fan_out > self.FAN_THRESHOLD:
            return "High fan-out suggests this node orchestrates too many concerns; consider decomposition"
        return "Moderate coupling; review for potential refactoring opportunities"

    def detect_layering_violations(self) -> list[LayeringViolation]:
        violations: list[LayeringViolation] = []
        layer_map = self.build_node_layer_map()

        for _layer_name, graph in self.index.software_graph.layers.items():
            for edge in graph.edges:
                source_layer = layer_map.get(edge.source)
                target_layer = layer_map.get(edge.target)
                if (
                    source_layer is not None
                    and target_layer is not None
                    and source_layer != target_layer
                    and edge.edge_type in {EdgeType.CALL, EdgeType.DATA, EdgeType.IMPORT}
                ):
                    violations.append(
                        LayeringViolation(
                            source_id=edge.source,
                            target_id=edge.target,
                            source_layer=source_layer,
                            target_layer=target_layer,
                            edge_type=edge.edge_type.value,
                            description=f"Cross-layer {edge.edge_type.value} edge from {source_layer} to {target_layer}",
                        )
                    )

        return violations

    def build_node_layer_map(self) -> dict[str, str]:
        node_layer: dict[str, str] = {}
        for layer_name, sg_graph in self.index.software_graph.layers.items():
            for node in sg_graph.nodes:
                if node.id not in node_layer:
                    node_layer[node.id] = layer_name.value
        return node_layer

    def detect_modules(self) -> list[ModuleInfo]:
        communities = self.index.detect_communities(layer=GraphLayer.CALL)
        call_graph = self.index.get_graph(GraphLayer.CALL)
        if call_graph is None:
            return []

        modules: list[ModuleInfo] = []
        for idx, community in enumerate(communities):
            internal = 0
            external = 0
            for u, v in call_graph.edges():
                if u in community and v in community:
                    internal += 1
                elif u in community or v in community:
                    external += 1

            total = internal + external
            cohesion = internal / total if total > 0 else 0.0

            modules.append(
                ModuleInfo(
                    module_id=idx,
                    node_ids=community,
                    node_count=len(community),
                    internal_edges=internal,
                    external_edges=external,
                    cohesion=cohesion,
                )
            )

        modules.sort(key=lambda m: m.cohesion, reverse=True)
        return modules

    def find_high_coupling_nodes(self) -> list[str]:
        high_out = self.index.high_fan_out_nodes(
            threshold=self.FAN_THRESHOLD, layer=GraphLayer.CALL
        )
        high_in = self.index.high_fan_in_nodes(threshold=self.FAN_THRESHOLD, layer=GraphLayer.CALL)
        return list(set(high_out) | set(high_in))

    def find_orphan_nodes(self) -> list[str]:
        call_graph = self.index.get_graph(GraphLayer.CALL)
        if call_graph is None:
            return []
        return [
            node_id
            for node_id in call_graph.nodes
            if call_graph.in_degree(node_id) == 0 and call_graph.out_degree(node_id) == 0
        ]
