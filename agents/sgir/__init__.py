"""SGIR agent package — graph-based software intelligence pipeline.

Re-exports the public SGIR pipeline operations so callers can
import them from :mod:`agents.sgir`. The operations themselves
live in :mod:`intelliqx_graph.operations`.
"""

from __future__ import annotations

from intelliqx_graph.operations import (
    build_software_graph,
    generate_code,
    optimize_graph,
    parse_repository,
    scan_repository,
)

__all__ = [
    "build_software_graph",
    "generate_code",
    "optimize_graph",
    "parse_repository",
    "scan_repository",
]
