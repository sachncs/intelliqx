"""Graph query helpers backed by NetworkX.

Provides a ``GraphIndex`` that wraps a ``SoftwareGraph`` in NetworkX
directed graphs for efficient traversal, reachability analysis,
community detection, and subgraph isomorphism.
"""

from __future__ import annotations

from typing import Any

import networkx as nx

from intelliqx_graph.models import (
    GraphLayer,
    SoftwareGraph,
)


class GraphIndex:
    """NetworkX-backed index over a ``SoftwareGraph``.

    Builds directed graphs per layer and provides convenience
    methods for common graph algorithms: reachability, critical
    paths, community detection, cycle detection, and subgraph
    isomorphism.
    """

    def __init__(self, software_graph: SoftwareGraph) -> None:
        self.sg = software_graph
        self.graphs: dict[GraphLayer, nx.DiGraph] = {}
        self.build()

    def build(self) -> None:
        for layer, sg_graph in self.sg.layers.items():
            g: nx.DiGraph = nx.DiGraph()
            for node in sg_graph.nodes:
                g.add_node(
                    node.id,
                    name=node.name,
                    purpose=node.purpose,
                    node_type=node.node_type.value,
                    language=node.language,
                    complexity=node.complexity.value,
                    is_dead=node.is_dead,
                )
            for edge in sg_graph.edges:
                g.add_edge(
                    edge.source,
                    edge.target,
                    edge_type=edge.edge_type.value,
                    weight=edge.weight,
                    label=edge.label,
                )
            self.graphs[layer] = g

    @property
    def software_graph(self) -> SoftwareGraph:
        return self.sg

    def get_graph(self, layer: GraphLayer) -> nx.DiGraph | None:
        """Return the NetworkX DiGraph for a specific layer."""
        return self.graphs.get(layer)

    def all_node_ids(self) -> set[str]:
        """Return all node IDs across all layers."""
        ids: set[str] = set()
        for g in self.graphs.values():
            ids.update(g.nodes)
        return ids

    # ------------------------------------------------------------------
    # Reachability
    # ------------------------------------------------------------------

    def reachable_from(
        self, node_id: str, *, layer: GraphLayer | None = None
    ) -> set[str]:
        """Return all nodes reachable from ``node_id``.

        If ``layer`` is specified, only that layer is traversed.
        Otherwise all layers are merged into a single directed graph.
        """
        g = self.merged_graph() if layer is None else self.graphs.get(layer)
        if g is None or node_id not in g:
            return set()
        return nx.descendants(g, node_id)

    def can_reach(
        self, source: str, target: str, *, layer: GraphLayer | None = None
    ) -> bool:
        """Return True if ``target`` is reachable from ``source``."""
        return target in self.reachable_from(source, layer=layer)

    # ------------------------------------------------------------------
    # Dead code detection
    # ------------------------------------------------------------------

    def find_dead_nodes(self, entry_points: list[str], *, layer: GraphLayer | None = None) -> set[str]:
        """Return node IDs unreachable from any entry point.

        Dead code = nodes that no entry point can reach.
        """
        g = self.merged_graph() if layer is None else self.graphs.get(layer)
        if g is None:
            return set()

        reachable: set[str] = set()
        for ep in entry_points:
            if ep in g:
                reachable.update(nx.descendants(g, ep))
                reachable.add(ep)
        return set(g.nodes) - reachable

    # ------------------------------------------------------------------
    # Critical path
    # ------------------------------------------------------------------

    def critical_path(
        self, source: str, target: str, *, layer: GraphLayer | None = None
    ) -> list[str] | None:
        """Find the longest weighted path from source to target.

        Returns the node ID sequence of the critical path, or
        ``None`` if no path exists.
        """
        g = self.merged_graph() if layer is None else self.graphs.get(layer)
        if g is None or source not in g or target not in g:
            return None
        try:
            # Negate weights for longest path via shortest path
            neg_g = g.copy()
            for _u, _v, d in neg_g.edges(data=True):
                d["neg_weight"] = -d.get("weight", 1.0)
            path = nx.shortest_path(neg_g, source, target, weight="neg_weight")
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    # ------------------------------------------------------------------
    # Community detection
    # ------------------------------------------------------------------

    def detect_communities(
        self, *, layer: GraphLayer | None = None
    ) -> list[set[str]]:
        """Detect communities using greedy modularity maximization.

        Returns a list of communities, each a set of node IDs.
        """
        g = self.merged_graph() if layer is None else self.graphs.get(layer)
        if g is None:
            return []

        undirected = g.to_undirected()
        communities = nx.community.greedy_modularity_communities(undirected)
        return [set(c) for c in communities]

    # ------------------------------------------------------------------
    # Cycle detection
    # ------------------------------------------------------------------

    def find_cycles(self, *, layer: GraphLayer | None = None) -> list[list[str]]:
        """Return all simple cycles in the graph."""
        g = self.merged_graph() if layer is None else self.graphs.get(layer)
        if g is None:
            return []
        try:
            return [list(c) for c in nx.simple_cycles(g)]
        except nx.NetworkXError:
            return []

    # ------------------------------------------------------------------
    # Subgraph isomorphism
    # ------------------------------------------------------------------

    def find_subgraph_isomorphisms(
        self, pattern: nx.DiGraph, *, layer: GraphLayer | None = None
    ) -> list[dict[str, str]]:
        """Find all subgraph isomorphisms of ``pattern`` in the target graph.

        Returns a list of mappings {pattern_node: target_node}.
        """
        g = self.merged_graph() if layer is None else self.graphs.get(layer)
        if g is None:
            return []
        matcher = nx.algorithms.isomorphism.DiGraphMatcher(g, pattern)
        return [m for m in matcher.subgraph_isomorphisms_iter()]

    # ------------------------------------------------------------------
    # Fan-in / Fan-out analysis
    # ------------------------------------------------------------------

    def fan_out(self, node_id: str, *, layer: GraphLayer | None = None) -> int:
        """Return the out-degree of a node."""
        g = self.merged_graph() if layer is None else self.graphs.get(layer)
        if g is None or node_id not in g:
            return 0
        return g.out_degree(node_id)

    def fan_in(self, node_id: str, *, layer: GraphLayer | None = None) -> int:
        """Return the in-degree of a node."""
        g = self.merged_graph() if layer is None else self.graphs.get(layer)
        if g is None or node_id not in g:
            return 0
        return g.in_degree(node_id)

    def high_fan_out_nodes(
        self, threshold: int = 10, *, layer: GraphLayer | None = None
    ) -> list[str]:
        """Return nodes with out-degree >= threshold (potential bottlenecks)."""
        g = self.merged_graph() if layer is None else self.graphs.get(layer)
        if g is None:
            return []
        return [n for n in g.nodes if g.out_degree(n) >= threshold]

    def high_fan_in_nodes(
        self, threshold: int = 10, *, layer: GraphLayer | None = None
    ) -> list[str]:
        """Return nodes with in-degree >= threshold (potential bottlenecks)."""
        g = self.merged_graph() if layer is None else self.graphs.get(layer)
        if g is None:
            return []
        return [n for n in g.nodes if g.in_degree(n) >= threshold]

    # ------------------------------------------------------------------
    # Topological sort
    # ------------------------------------------------------------------

    def topological_order(self, *, layer: GraphLayer | None = None) -> list[str] | None:
        """Return a topological ordering of nodes, or None if cyclic."""
        g = self.merged_graph() if layer is None else self.graphs.get(layer)
        if g is None:
            return []
        try:
            return list(nx.topological_sort(g))
        except nx.NetworkXUnfeasible:
            return None

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return summary statistics for the indexed graph."""
        result: dict[str, Any] = {
            "total_layers": len(self.graphs),
            "layers": {},
        }
        for layer, g in self.graphs.items():
            result["layers"][layer.value] = {
                "nodes": g.number_of_nodes(),
                "edges": g.number_of_edges(),
                "density": nx.density(g) if g.number_of_nodes() > 1 else 0.0,
                "is_dag": nx.is_directed_acyclic_graph(g),
                "num_strongly_connected": nx.number_strongly_connected_components(g),
            }
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def merged_graph(self) -> nx.DiGraph:
        """Merge all layer graphs into a single directed graph."""
        merged = nx.DiGraph()
        for g in self.graphs.values():
            merged.update(g)
        return merged
