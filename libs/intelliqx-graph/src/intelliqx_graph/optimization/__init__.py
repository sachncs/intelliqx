from __future__ import annotations

from intelliqx_graph.optimization.passes import (
    clean_dependency_cycles,
    detect_duplicates,
    inline_trivial_nodes,
    parallelize_independent_branches,
    reduce_complexity,
    remove_dead_nodes,
)
from intelliqx_graph.optimization.pipeline import OptimizationPipeline
from intelliqx_graph.optimization.verification import VerificationAgent, VerificationReport

__all__ = [
    "OptimizationPipeline",
    "VerificationAgent",
    "VerificationReport",
    "clean_dependency_cycles",
    "detect_duplicates",
    "inline_trivial_nodes",
    "parallelize_independent_branches",
    "reduce_complexity",
    "remove_dead_nodes",
]
