"""Software Graph Intermediate Representation (SGIR).

The SGIR is the canonical representation of software systems as semantic
execution graphs. Every repository, regardless of programming language,
is compiled into a language-independent graph where nodes represent
computations and edges represent the flow of data, control, and
dependencies.
"""

from intelliqx_graph.models import (
    EdgeType,
    GraphLayer,
    SGIRGraph,
    SGIRNode,
    SoftwareGraph,
)

__all__ = [
    "EdgeType",
    "GraphLayer",
    "SGIRGraph",
    "SGIRNode",
    "SoftwareGraph",
]
