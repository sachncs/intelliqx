"""SGIR core models.

Defines the Software Graph Intermediate Representation: nodes, edges,
multi-layer graphs, and the top-level container. Every field is
documented and uses ``extra="forbid"`` to keep the input boundary
explicit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EdgeType(str, Enum):
    """Types of edges in the SGIR.

    Each variant maps to a distinct semantic relationship between nodes.
    """

    CALL = "call"
    DATA = "data"
    CONTROL = "control"
    DEPENDENCY = "dependency"
    EVENT = "event"
    NETWORK = "network"
    DATABASE = "database"
    STATE_TRANSITION = "state_transition"
    IMPORT = "import"
    INHERIT = "inherit"
    IMPLEMENT = "implement"
    COMPOSE = "compose"


class GraphLayer(str, Enum):
    """The eight interconnected graph layers.

    Together these form the complete semantic model of the software.
    """

    CALL = "call"
    DATA_FLOW = "data_flow"
    CONTROL_FLOW = "control_flow"
    DEPENDENCY = "dependency"
    STATE_TRANSITION = "state_transition"
    RESOURCE = "resource"
    SECURITY = "security"
    DEPLOYMENT = "deployment"


class NodeType(str, Enum):
    """Semantic classification of SGIR nodes."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    MODULE = "module"
    PACKAGE = "package"
    SERVICE = "service"
    ENDPOINT = "endpoint"
    EVENT_HANDLER = "event_handler"
    MIDDLEWARE = "middleware"
    DATAMODEL = "datamodel"
    CONFIG = "config"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


class ComplexityEstimate(str, Enum):
    """Rough computational complexity of a node."""

    CONSTANT = "O(1)"
    LOGARITHMIC = "O(log n)"
    LINEAR = "O(n)"
    LINEARITHMIC = "O(n log n)"
    QUADRATIC = "O(n^2)"
    CUBIC = "O(n^3)"
    EXPONENTIAL = "O(2^n)"
    UNKNOWN = "unknown"


class SecurityBoundary(str, Enum):
    """Security trust boundary classification."""

    NONE = "none"
    AUTHENTICATED = "authenticated"
    AUTHORIZED = "authorized"
    ADMIN = "admin"
    INTERNAL = "internal"
    EXTERNAL = "external"
    SANDBOXED = "sandboxed"


# ---------------------------------------------------------------------------
# SGIR Node
# ---------------------------------------------------------------------------


class SourceLocation(BaseModel):
    """Location in the original source code."""

    model_config = ConfigDict(extra="forbid")

    file_path: str
    line_start: int
    line_end: int
    column_start: int = 0
    column_end: int = 0


class SGIRNode(BaseModel):
    """A single node in the Software Graph IR.

    Each node represents a computation that transforms one state into
    another. The node captures semantic information rather than syntax.

    ``f : State -> State``
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    purpose: str = ""
    node_type: NodeType = NodeType.UNKNOWN
    language: str = "unknown"
    source_location: SourceLocation | None = None

    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)

    side_effects: list[str] = Field(default_factory=list)
    external_dependencies: list[str] = Field(default_factory=list)
    resource_usage: dict[str, Any] = Field(default_factory=dict)

    complexity: ComplexityEstimate = ComplexityEstimate.UNKNOWN
    failure_modes: list[str] = Field(default_factory=list)
    security_boundary: SecurityBoundary = SecurityBoundary.NONE

    ownership: str | None = None
    test_coverage: float = 0.0
    documentation: str = ""
    performance_metrics: dict[str, Any] = Field(default_factory=dict)

    # Metadata for optimization tracking
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_dead: bool = False
    is_duplicate: bool = False
    optimization_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# SGIR Edge
# ---------------------------------------------------------------------------


class SGIREdge(BaseModel):
    """An edge in the Software Graph IR.

    Edges represent the movement of control, data, events, or
    dependencies between computations.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    edge_type: EdgeType
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    label: str = ""


# ---------------------------------------------------------------------------
# SGIR Graph (single layer)
# ---------------------------------------------------------------------------


class SGIRGraph(BaseModel):
    """A single graph layer containing nodes and edges.

    Each layer represents one semantic dimension of the software.
    """

    model_config = ConfigDict(extra="forbid")

    layer: GraphLayer
    nodes: list[SGIRNode] = Field(default_factory=list)
    edges: list[SGIREdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)


# ---------------------------------------------------------------------------
# Repository Metadata
# ---------------------------------------------------------------------------


class RepositoryMetadata(BaseModel):
    """Metadata about the source repository being analyzed."""

    model_config = ConfigDict(extra="forbid")

    name: str
    root_path: str
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    build_systems: list[str] = Field(default_factory=list)
    architecture_style: str = "unknown"
    total_files: int = 0
    total_lines: int = 0
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    extra: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Software Graph (multi-layer container)
# ---------------------------------------------------------------------------


class SoftwareGraph(BaseModel):
    """Multi-layer container — the complete semantic model of software.

    The ``SoftwareGraph`` holds the repository metadata and up to eight
    ``SGIRGraph`` layers. Each layer represents one semantic dimension:
    call graph, data flow, control flow, dependency, state transition,
    resource, security, and deployment.
    """

    model_config = ConfigDict(extra="forbid")

    repository: RepositoryMetadata
    layers: dict[GraphLayer, SGIRGraph] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_layer(self, layer: GraphLayer) -> SGIRGraph | None:
        """Return the specified graph layer, or ``None`` if absent."""
        return self.layers.get(layer)

    def add_layer(self, graph: SGIRGraph) -> None:
        """Add or replace a graph layer."""
        self.layers[graph.layer] = graph

    @property
    def total_nodes(self) -> int:
        return sum(g.node_count for g in self.layers.values())

    @property
    def total_edges(self) -> int:
        return sum(g.edge_count for g in self.layers.values())

    @property
    def layers_present(self) -> list[GraphLayer]:
        return list(self.layers.keys())

    def all_nodes(self) -> list[SGIRNode]:
        """Return all nodes across all layers (may contain duplicates)."""
        nodes: list[SGIRNode] = []
        for graph in self.layers.values():
            nodes.extend(graph.nodes)
        return nodes

    def find_node(self, node_id: str) -> SGIRNode | None:
        """Find a node by ID across all layers."""
        for graph in self.layers.values():
            for node in graph.nodes:
                if node.id == node_id:
                    return node
        return None
