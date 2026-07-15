from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from intelliqx_graph.models import (
    SoftwareGraph,
)
from intelliqx_graph.query import GraphIndex


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class VerificationReport(BaseModel):
    behavior_preserved: bool
    nodes_added: int
    nodes_removed: int
    edges_added: int
    edges_removed: int
    risk_level: str
    findings: list[str] = Field(default_factory=list)


def node_ids(graph: SoftwareGraph) -> set[str]:
    ids: set[str] = set()
    for lg in graph.layers.values():
        ids.update(lg.node_ids)
    return ids


def edge_keys(graph: SoftwareGraph) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for lg in graph.layers.values():
        for e in lg.edges:
            keys.add((e.source, e.target))
    return keys


def build_trace_set(
    graph: SoftwareGraph,
    graph_index: GraphIndex,
    entry_points: list[str],
    max_depth: int = 50,
) -> set[tuple[str, ...]]:
    traces: set[tuple[str, ...]] = set()
    all_ids = node_ids(graph)

    for ep in entry_points:
        if ep not in all_ids:
            continue
        dfs_traces(graph_index, ep, [], traces, all_ids, set(), max_depth)

    return traces


def dfs_traces(
    graph_index: GraphIndex,
    current: str,
    path: list[str],
    traces: set[tuple[str, ...]],
    valid_ids: set[str],
    visited: set[str],
    depth_remaining: int,
) -> None:
    if depth_remaining <= 0 or current in visited:
        traces.add(tuple(path + [current]))
        return

    visited.add(current)
    path.append(current)

    successors = [
        n for n in graph_index.reachable_from(current)
        if n in valid_ids
    ]

    if not successors:
        traces.add(tuple(path))
    else:
        for s in successors[:10]:
            dfs_traces(graph_index, s, path, traces, valid_ids, visited, depth_remaining - 1)

    path.pop()
    visited.discard(current)


class VerificationAgent:
    def __init__(
        self,
        before: SoftwareGraph,
        after: SoftwareGraph,
        entry_points: list[str],
    ) -> None:
        self.before = before
        self.after = after
        self.entry_points = entry_points
        self.before_index = GraphIndex(before)
        self.after_index = GraphIndex(after)

    def verify(self) -> VerificationReport:
        before_nodes = node_ids(self.before)
        after_nodes = node_ids(self.after)
        before_edges = edge_keys(self.before)
        after_edges = edge_keys(self.after)

        nodes_added = len(after_nodes - before_nodes)
        nodes_removed = len(before_nodes - after_nodes)
        edges_added = len(after_edges - before_edges)
        edges_removed = len(before_edges - after_edges)

        findings: list[str] = []
        behavior_preserved = True

        traces_before = build_trace_set(
            self.before, self.before_index, self.entry_points,
        )
        traces_after = build_trace_set(
            self.after, self.after_index, self.entry_points,
        )

        lost_traces = traces_before - traces_after
        if lost_traces:
            behavior_preserved = False
            findings.append(
                f"Lost {len(lost_traces)} execution traces after optimization"
            )

        reachable_before = set()
        for ep in self.entry_points:
            reachable_before.update(self.before_index.reachable_from(ep))
            if ep in before_nodes:
                reachable_before.add(ep)

        removed_reachable = before_nodes - after_nodes
        improperly_removed = removed_reachable & reachable_before
        if improperly_removed:
            behavior_preserved = False
            findings.append(
                f"Removed {len(improperly_removed)} reachable nodes: "
                f"{sorted(improperly_removed)[:5]}"
            )

        risk = self.assess_risk(
            nodes_added, nodes_removed, edges_added, edges_removed,
            behavior_preserved, improperly_removed,
        )

        if nodes_removed > 0:
            findings.append(f"Removed {nodes_removed} nodes across all layers")
        if nodes_added > 0:
            findings.append(f"Added {nodes_added} nodes across all layers")
        if edges_removed > 0:
            findings.append(f"Removed {edges_removed} edges across all layers")
        if edges_added > 0:
            findings.append(f"Added {edges_added} edges across all layers")

        return VerificationReport(
            behavior_preserved=behavior_preserved,
            nodes_added=nodes_added,
            nodes_removed=nodes_removed,
            edges_added=edges_added,
            edges_removed=edges_removed,
            risk_level=risk.value,
            findings=findings,
        )

    def assess_risk(
        self,
        nodes_added: int,
        nodes_removed: int,
        edges_added: int,
        edges_removed: int,
        behavior_preserved: bool,
        improperly_removed: set[str],
    ) -> RiskLevel:
        if improperly_removed:
            return RiskLevel.CRITICAL

        if not behavior_preserved:
            return RiskLevel.HIGH

        total_changes = nodes_added + nodes_removed + edges_added + edges_removed
        if total_changes > 50:
            return RiskLevel.MEDIUM
        if total_changes > 10:
            return RiskLevel.LOW
        return RiskLevel.LOW
