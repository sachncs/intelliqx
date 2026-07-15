from __future__ import annotations

from enum import Enum
from itertools import pairwise
from typing import ClassVar

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from intelliqx_graph.models import GraphLayer, SecurityBoundary
from intelliqx_graph.query import GraphIndex

MAX_SENSITIVE_FLOWS: int = 50
BOUNDARY_CROSSING_WEIGHT: float = 2.0


class VulnerabilityType(str, Enum):
    UNSANITIZED_INPUT = "unsanitized_input"
    SQL_INJECTION = "sql_injection"
    TRUST_BOUNDARY_CROSSING = "trust_boundary_crossing"
    UNVALIDATED_DEPENDENCY = "unvalidated_dependency"
    SENSITIVE_DATA_EXPOSURE = "sensitive_data_exposure"
    INSUFFICIENT_AUTH = "insufficient_authorization"


class SensitiveDataFlow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_node: str
    target_node: str
    path: list[str]
    source_boundary: str
    target_boundary: str
    crosses_boundary: bool
    edge_types: list[str] = Field(default_factory=list)


class TrustBoundaryCrossing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    target_id: str
    source_boundary: str
    target_boundary: str
    edge_type: str
    risk_level: str
    description: str


class Vulnerability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vulnerability_type: VulnerabilityType
    node_id: str
    node_name: str
    severity: str
    description: str
    affected_data_flow: list[str] = Field(default_factory=list)
    recommendation: str


class SecurityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sensitive_data_flows: list[SensitiveDataFlow] = Field(default_factory=list)
    trust_boundary_crossings: list[TrustBoundaryCrossing] = Field(default_factory=list)
    vulnerabilities: list[Vulnerability] = Field(default_factory=list)
    nodes_by_boundary: dict[str, int] = Field(default_factory=dict)
    total_nodes_analyzed: int = 0
    boundary_crossing_count: int = 0
    risk_score: float = 0.0


class SecurityAgent:
    SQL_PATTERNS: ClassVar[set[str]] = {"query", "execute", "select", "insert", "update", "delete", "sql", "cursor"}
    SANITIZE_PATTERNS: ClassVar[set[str]] = {"sanitize", "escape", "validate", "clean", "encode", "parameterize"}
    SENSITIVE_KEYWORDS: ClassVar[set[str]] = {"password", "token", "secret", "key", "credential", "ssn", "email", "auth"}
    INPUT_KEYWORDS: ClassVar[set[str]] = {"receive", "parse", "read", "input", "request", "param"}
    UNSAFE_OUTPUT_KEYWORDS: ClassVar[set[str]] = {"html", "response", "exec", "query", "system"}
    SENSITIVE_NAME_KEYWORDS: ClassVar[set[str]] = {"password", "secret", "token", "key"}
    RISK_SCORES: ClassVar[dict[str, float]] = {"high": 3, "medium": 2, "low": 1}
    SEVERITY_VALUES: ClassVar[dict[str, float]] = {"high": 10.0, "medium": 5.0, "low": 1.0}

    def __init__(self, graph_index: GraphIndex) -> None:
        self.index = graph_index

    def analyze(self) -> SecurityReport:
        security_graph = self.index.get_graph(GraphLayer.SECURITY)
        data_flow_graph = self.index.get_graph(GraphLayer.DATA_FLOW)
        call_graph = self.index.get_graph(GraphLayer.CALL)

        if security_graph is None and data_flow_graph is None:
            return SecurityReport()

        sg = self.index.software_graph
        boundary_map = self.build_boundary_map(sg)
        nodes_by_boundary = self.count_by_boundary(boundary_map)

        sensitive_flows = self.trace_sensitive_data_flows(
            data_flow_graph or security_graph, boundary_map
        )
        crossings = self.detect_trust_boundary_crossings(security_graph, boundary_map)
        vulns = self.detect_vulnerabilities(call_graph, data_flow_graph, boundary_map)

        boundary_crossings = len(crossings)
        risk_score = self.compute_risk_score(vulns, boundary_crossings)

        total_nodes = 0
        if security_graph:
            total_nodes = security_graph.number_of_nodes()
        elif data_flow_graph:
            total_nodes = data_flow_graph.number_of_nodes()

        return SecurityReport(
            sensitive_data_flows=sensitive_flows,
            trust_boundary_crossings=crossings,
            vulnerabilities=vulns,
            nodes_by_boundary=nodes_by_boundary,
            total_nodes_analyzed=total_nodes,
            boundary_crossing_count=boundary_crossings,
            risk_score=risk_score,
        )

    def build_boundary_map(self, sg: object) -> dict[str, SecurityBoundary]:
        boundary_map: dict[str, SecurityBoundary] = {}
        for layer_graph in sg.layers.values():  # type: ignore[union-attr]
            for node in layer_graph.nodes:
                if node.id not in boundary_map:
                    boundary_map[node.id] = node.security_boundary
        return boundary_map

    def count_by_boundary(self, boundary_map: dict[str, SecurityBoundary]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for boundary in boundary_map.values():
            key = boundary.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def trace_sensitive_data_flows(
        self,
        data_flow: nx.DiGraph | None,
        boundary_map: dict[str, SecurityBoundary],
    ) -> list[SensitiveDataFlow]:
        flows: list[SensitiveDataFlow] = []
        if data_flow is None:
            return flows

        sg = self.index.software_graph
        source_nodes = [
            n for n in data_flow.nodes
            if data_flow.in_degree(n) == 0
        ]

        for source in source_nodes:
            node = sg.find_node(source)
            if node is None:
                continue

            name_lower = node.name.lower()
            is_sensitive = any(kw in name_lower for kw in self.SENSITIVE_KEYWORDS)
            if not is_sensitive and node.security_boundary in {
                SecurityBoundary.AUTHENTICATED, SecurityBoundary.AUTHORIZED, SecurityBoundary.ADMIN
            }:
                is_sensitive = True
            if not is_sensitive:
                continue

            for target in nx.descendants(data_flow, source):
                try:
                    path = nx.shortest_path(data_flow, source, target)
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue

                source_boundary = boundary_map.get(source, SecurityBoundary.NONE).value
                target_boundary = boundary_map.get(target, SecurityBoundary.NONE).value
                crosses = source_boundary != target_boundary and source_boundary != "none"

                edge_types: list[str] = []
                for u, v in pairwise(path):
                    edge_data = data_flow[u][v]
                    et = edge_data.get("edge_type", "")
                    if et not in edge_types:
                        edge_types.append(et)

                flows.append(SensitiveDataFlow(
                    source_node=source,
                    target_node=target,
                    path=path,
                    source_boundary=source_boundary,
                    target_boundary=target_boundary,
                    crosses_boundary=crosses,
                    edge_types=edge_types,
                ))

        return flows[:MAX_SENSITIVE_FLOWS]

    def detect_trust_boundary_crossings(
        self,
        security_graph: nx.DiGraph | None,
        boundary_map: dict[str, SecurityBoundary],
    ) -> list[TrustBoundaryCrossing]:
        crossings: list[TrustBoundaryCrossing] = []
        if security_graph is None:
            return crossings

        for source, target in security_graph.edges():
            src_boundary = boundary_map.get(source, SecurityBoundary.NONE)
            tgt_boundary = boundary_map.get(target, SecurityBoundary.NONE)

            if src_boundary == tgt_boundary:
                continue
            if src_boundary == SecurityBoundary.NONE and tgt_boundary == SecurityBoundary.NONE:
                continue

            edge_data = security_graph[source][target]
            edge_type = edge_data.get("edge_type", "unknown")

            risk_level = self.crossing_risk(src_boundary, tgt_boundary)

            crossings.append(TrustBoundaryCrossing(
                source_id=source,
                target_id=target,
                source_boundary=src_boundary.value,
                target_boundary=tgt_boundary.value,
                edge_type=edge_type,
                risk_level=risk_level,
                description=f"Data flows from {src_boundary.value} to {tgt_boundary.value} boundary",
            ))

        crossings.sort(key=lambda c: self.RISK_SCORES.get(c.risk_level, 0), reverse=True)
        return crossings

    def crossing_risk(self, source: SecurityBoundary, target: SecurityBoundary) -> str:
        if (
            (source == SecurityBoundary.NONE or source == SecurityBoundary.EXTERNAL)
            and target in {SecurityBoundary.AUTHENTICATED, SecurityBoundary.AUTHORIZED, SecurityBoundary.ADMIN}
        ):
            return "high"
        if source == SecurityBoundary.ADMIN and target != SecurityBoundary.ADMIN:
            return "high"
        if source == SecurityBoundary.INTERNAL and target == SecurityBoundary.EXTERNAL:
            return "medium"
        return "low"

    def detect_vulnerabilities(
        self,
        call_graph: nx.DiGraph | None,
        data_flow: nx.DiGraph | None,
        boundary_map: dict[str, SecurityBoundary],
    ) -> list[Vulnerability]:
        vulns: list[Vulnerability] = []
        sg = self.index.software_graph

        for node_id in (call_graph.nodes if call_graph else []):
            node = sg.find_node(node_id)
            if node is None:
                continue

            node_name_lower = node.name.lower()

            if self.is_sql_injection_risk(node):
                vulns.append(Vulnerability(
                    vulnerability_type=VulnerabilityType.SQL_INJECTION,
                    node_id=node_id,
                    node_name=node.name,
                    severity="high",
                    description=f"Node '{node.name}' may execute SQL with unsanitized input",
                    affected_data_flow=[node_id],
                    recommendation="Use parameterized queries and input validation",
                ))

            if self.is_unsanitized_input(node):
                vulns.append(Vulnerability(
                    vulnerability_type=VulnerabilityType.UNSANITIZED_INPUT,
                    node_id=node_id,
                    node_name=node.name,
                    severity="medium",
                    description=f"Node '{node.name}' accepts input that may not be sanitized",
                    affected_data_flow=[node_id],
                    recommendation="Validate and sanitize all external inputs",
                ))

            if (
                boundary_map.get(node_id, SecurityBoundary.NONE) == SecurityBoundary.NONE
                and any(kw in node_name_lower for kw in self.SENSITIVE_NAME_KEYWORDS)
            ):
                vulns.append(Vulnerability(
                    vulnerability_type=VulnerabilityType.SENSITIVE_DATA_EXPOSURE,
                    node_id=node_id,
                    node_name=node.name,
                    severity="high",
                    description=f"Node '{node.name}' handles sensitive data without a security boundary",
                    affected_data_flow=[node_id],
                    recommendation="Apply appropriate security boundaries to sensitive data handlers",
                ))

        if data_flow is not None:
            for source, target in data_flow.edges():
                src_boundary = boundary_map.get(source, SecurityBoundary.NONE)
                tgt_boundary = boundary_map.get(target, SecurityBoundary.NONE)
                if (
                    src_boundary == SecurityBoundary.NONE
                    and tgt_boundary != SecurityBoundary.NONE
                    and tgt_boundary != SecurityBoundary.EXTERNAL
                ):
                    source_node = sg.find_node(source)
                    if source_node and not self.has_sanitization(source_node):
                        vulns.append(Vulnerability(
                            vulnerability_type=VulnerabilityType.TRUST_BOUNDARY_CROSSING,
                            node_id=source,
                            node_name=source_node.name,
                            severity="medium",
                            description=f"Untrusted node '{source_node.name}' feeds into {tgt_boundary.value} boundary",
                            affected_data_flow=[source, target],
                            recommendation="Validate and sanitize data crossing trust boundaries",
                        ))

        vulns.sort(key=lambda v: self.SEVERITY_VALUES.get(v.severity, 0), reverse=True)
        return vulns

    def is_sql_injection_risk(self, node: object) -> bool:
        name_lower = node.name.lower()  # type: ignore[union-attr]
        has_sql = any(p in name_lower for p in self.SQL_PATTERNS)
        if not has_sql:
            return False
        inputs_lower = [i.lower() for i in node.inputs]  # type: ignore[union-attr]
        has_raw_input = any(
            "string" in inp or "raw" in inp or "text" in inp or "input" in inp
            for inp in inputs_lower
        )
        return has_raw_input and not self.has_sanitization(node)

    def is_unsanitized_input(self, node: object) -> bool:
        name_lower = node.name.lower()  # type: ignore[union-attr]
        has_input = any(kw in name_lower for kw in self.INPUT_KEYWORDS)
        if not has_input:
            return False
        outputs = [o.lower() for o in node.outputs]  # type: ignore[union-attr]
        has_unsafe_output = any(
            kw in out for kw in self.UNSAFE_OUTPUT_KEYWORDS
            for out in outputs
        )
        return has_unsafe_output and not self.has_sanitization(node)

    def has_sanitization(self, node: object) -> bool:
        name_lower = node.name.lower()  # type: ignore[union-attr]
        postconditions = [p.lower() for p in node.postconditions]  # type: ignore[union-attr]
        return (
            any(p in name_lower for p in self.SANITIZE_PATTERNS)
            or any(any(s in pc for s in self.SANITIZE_PATTERNS) for pc in postconditions)
        )

    def compute_risk_score(self, vulns: list[Vulnerability], crossing_count: int) -> float:
        vuln_score = sum(self.SEVERITY_VALUES.get(v.severity, 0.0) for v in vulns)
        crossing_score = crossing_count * BOUNDARY_CROSSING_WEIGHT
        return vuln_score + crossing_score
