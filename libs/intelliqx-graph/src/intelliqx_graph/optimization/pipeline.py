from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from intelliqx_graph.models import SoftwareGraph
from intelliqx_graph.optimization.passes import (
    clean_dependency_cycles,
    detect_duplicates,
    inline_trivial_nodes,
    parallelize_independent_branches,
    reduce_complexity,
    remove_dead_nodes,
)
from intelliqx_graph.optimization.verification import (
    DEFAULT_RISK_LEVEL,
    VerificationAgent,
    VerificationReport,
)
from intelliqx_graph.query import GraphIndex


class OptimizationResult(BaseModel):
    before: SoftwareGraph
    after: SoftwareGraph
    verification_reports: list[VerificationReport] = Field(default_factory=list)
    duplicate_pairs: list[tuple[str, str]] = Field(default_factory=list)
    parallel_branches: list[list[str]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class OptimizationPipeline:
    def __init__(
        self,
        graph: SoftwareGraph,
        graph_index: GraphIndex,
        entry_points: list[str],
        target_language: str,
    ) -> None:
        self.graph = graph
        self.graph_index = graph_index
        self.entry_points = entry_points
        self.target_language = target_language
        self.reports: list[VerificationReport] = []
        self.duplicate_pairs: list[tuple[str, str]] = []
        self.parallel_branches: list[list[str]] = []

    def run(self) -> OptimizationResult:
        original = copy.deepcopy(self.graph)
        working = copy.deepcopy(self.graph)

        working = self.apply_pass(
            working, "dead_code_removal",
            lambda g: remove_dead_nodes(g, self.graph_index, self.entry_points),
        )

        self.duplicate_pairs = detect_duplicates(working, self.graph_index)

        working = self.apply_pass(
            working, "inline_trivial",
            lambda g: inline_trivial_nodes(g, self.graph_index),
        )

        working = self.apply_pass(
            working, "reduce_complexity",
            lambda g: reduce_complexity(g, self.graph_index),
        )

        working = self.apply_pass(
            working, "clean_cycles",
            lambda g: clean_dependency_cycles(g, self.graph_index),
        )

        self.parallel_branches = parallelize_independent_branches(
            working, self.graph_index,
        )

        summary = self.build_summary(original, working)

        return OptimizationResult(
            before=original,
            after=working,
            verification_reports=self.reports,
            duplicate_pairs=self.duplicate_pairs,
            parallel_branches=self.parallel_branches,
            summary=summary,
        )

    def apply_pass(
        self,
        graph: SoftwareGraph,
        pass_name: str,
        pass_fn: Callable[[SoftwareGraph], SoftwareGraph],
    ) -> SoftwareGraph:
        result = pass_fn(graph)

        agent = VerificationAgent(
            before=graph,
            after=result,
            entry_points=self.entry_points,
        )
        report = agent.verify()
        self.reports.append(report)

        if not report.behavior_preserved:
            return graph

        return result

    def build_summary(
        self,
        before: SoftwareGraph,
        after: SoftwareGraph,
    ) -> dict[str, Any]:
        return {
            "target_language": self.target_language,
            "nodes_before": before.total_nodes,
            "nodes_after": after.total_nodes,
            "edges_before": before.total_edges,
            "edges_after": after.total_edges,
            "node_reduction": before.total_nodes - after.total_nodes,
            "edge_reduction": before.total_edges - after.total_edges,
            "pass_count": len(self.reports),
            "all_behavior_preserved": all(
                r.behavior_preserved for r in self.reports
            ),
            "max_risk_level": max(
                (r.risk_level for r in self.reports),
                default=DEFAULT_RISK_LEVEL,
            ),
            "duplicate_pairs_found": len(self.duplicate_pairs),
            "parallel_branches_found": len(self.parallel_branches),
        }
