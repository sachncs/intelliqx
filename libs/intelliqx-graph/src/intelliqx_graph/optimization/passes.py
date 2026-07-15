from __future__ import annotations

import copy

import networkx as nx

from intelliqx_graph.models import (
    ComplexityEstimate,
    EdgeType,
    SGIREdge,
    SGIRGraph,
    SGIRNode,
    SoftwareGraph,
)
from intelliqx_graph.query import GraphIndex


def _rebuild_graph(
    graph: SGIRGraph,
    nodes: list[SGIRNode],
    edges: list[SGIREdge],
) -> SGIRGraph:
    return SGIRGraph(
        layer=graph.layer,
        nodes=nodes,
        edges=edges,
        metadata=graph.metadata,
    )


def _node_map(graph: SGIRGraph) -> dict[str, SGIRNode]:
    return {n.id: n for n in graph.nodes}



# ------------------------------------------------------------------
# remove_dead_nodes
# ------------------------------------------------------------------

def remove_dead_nodes(
    graph: SoftwareGraph,
    graph_index: GraphIndex,
    entry_points: list[str],
) -> SoftwareGraph:
    working = copy.deepcopy(graph)
    dead_ids = graph_index.find_dead_nodes(entry_points)

    for layer_graph in working.layers.values():
        node_ids = layer_graph.node_ids
        dead_in_layer = dead_ids & node_ids
        if not dead_in_layer:
            continue
        surviving_nodes = [n for n in layer_graph.nodes if n.id not in dead_in_layer]
        surviving_edges = [
            e for e in layer_graph.edges
            if e.source not in dead_in_layer and e.target not in dead_in_layer
        ]
        for n in layer_graph.nodes:
            if n.id in dead_in_layer:
                n.is_dead = True
        working.layers[layer_graph.layer] = _rebuild_graph(
            layer_graph, surviving_nodes, surviving_edges,
        )

    return working


# ------------------------------------------------------------------
# detect_duplicates
# ------------------------------------------------------------------

def _subgraph_signature(
    graph: SGIRGraph,
    node_ids: frozenset[str],
) -> tuple[str, ...]:
    node_map = _node_map(graph)
    sub_edges = [
        (e.source, e.target, e.edge_type)
        for e in graph.edges
        if e.source in node_ids and e.target in node_ids
    ]
    sorted_edges = sorted(sub_edges, key=lambda e: (e[0], e[1]))
    return tuple(
        (node_map[nid].node_type.value if nid in node_map else "unknown", src, tgt, et.value)
        for nid, src, tgt, et in [
            (nid, s, t, e) for s, t, e in sorted_edges for nid in (s, t)
        ]
    )


def detect_duplicates(
    graph: SoftwareGraph,
    graph_index: GraphIndex,
) -> list[tuple[str, str]]:
    seen_signatures: dict[tuple[str, ...], list[str]] = {}
    duplicates: list[tuple[str, str]] = []

    for layer_graph in graph.layers.values():
        adjacency: dict[str, set[str]] = {}
        for e in layer_graph.edges:
            adjacency.setdefault(e.source, set()).add(e.target)

        visited: set[str] = set()
        for node in layer_graph.nodes:
            if node.id in visited:
                continue
            component = _bfs_component(node.id, adjacency)
            if len(component) < 2:
                visited.update(component)
                continue
            component_frozen = frozenset(component)
            sig = _subgraph_signature(layer_graph, component_frozen)
            if sig in seen_signatures:
                existing = seen_signatures[sig][0]
                duplicates.append((existing, node.id))
            else:
                seen_signatures[sig] = [node.id]
            visited.update(component)

    return duplicates


def _bfs_component(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    component: set[str] = set()
    queue = [start]
    while queue:
        current = queue.pop()
        if current in component:
            continue
        component.add(current)
        for neighbor in adjacency.get(current, set()):
            if neighbor not in component:
                queue.append(neighbor)
    return component


# ------------------------------------------------------------------
# inline_trivial_nodes
# ------------------------------------------------------------------

def inline_trivial_nodes(
    graph: SoftwareGraph,
    graph_index: GraphIndex,
    threshold: int = 5,
) -> SoftwareGraph:
    working = copy.deepcopy(graph)

    for layer_graph in working.layers.values():
        inline_candidates: set[str] = set()
        for node in layer_graph.nodes:
            out_degree = graph_index.fan_out(node.id, layer=layer_graph.layer)
            if out_degree == 1 and _is_simple_node(node, threshold):
                inline_candidates.add(node.id)

        if not inline_candidates:
            continue

        node_map = _node_map(layer_graph)
        edge_map: dict[str, list[SGIREdge]] = {}
        for e in layer_graph.edges:
            edge_map.setdefault(e.source, []).append(e)

        surviving_nodes = [n for n in layer_graph.nodes if n.id not in inline_candidates]
        new_edges: list[SGIREdge] = []
        inlined_map: dict[str, str] = {}

        for cid in inline_candidates:
            out_edges = edge_map.get(cid, [])
            if out_edges:
                inlined_map[cid] = out_edges[0].target

        for e in layer_graph.edges:
            if e.source in inline_candidates or e.target in inline_candidates:
                continue
            new_edges.append(e)

        for cid in inline_candidates:
            in_edges = [
                e for e in layer_graph.edges
                if e.target == cid and e.source not in inline_candidates
            ]
            target = inlined_map.get(cid)
            if target is None:
                continue
            for ie in in_edges:
                node_map[cid].optimization_notes.append(f"inlined into {target}")
                new_edges.append(SGIREdge(
                    source=ie.source,
                    target=target,
                    edge_type=ie.edge_type,
                    weight=ie.weight,
                    label=f"inlined:{node_map[cid].name}",
                ))

        working.layers[layer_graph.layer] = _rebuild_graph(
            layer_graph, surviving_nodes, new_edges,
        )

    return working


def _is_simple_node(node: SGIRNode, threshold: int) -> bool:
    complexity_order = {
        "O(1)": 0,
        "O(log n)": 1,
        "O(n)": 2,
        "O(n log n)": 3,
        "O(n^2)": 4,
        "O(n^3)": 5,
        "O(2^n)": 6,
        "unknown": 7,
    }
    return (
        complexity_order.get(node.complexity.value, 7) <= threshold
        and not node.side_effects
        and not node.failure_modes
    )


# ------------------------------------------------------------------
# parallelize_independent_branches
# ------------------------------------------------------------------

def parallelize_independent_branches(
    graph: SoftwareGraph,
    graph_index: GraphIndex,
) -> list[list[str]]:
    independent_branches: list[list[str]] = []

    for layer_graph in graph.layers.values():
        nx_graph = nx.DiGraph()
        for node in layer_graph.nodes:
            nx_graph.add_node(node.id)
        for edge in layer_graph.edges:
            nx_graph.add_edge(edge.source, edge.target)

        if nx.is_directed_acyclic_graph(nx_graph):
            levels = _parallel_levels(nx_graph)
            for level in levels:
                if len(level) > 1:
                    independent_branches.append(sorted(level))

        sccs = list(nx.strongly_connected_components(nx_graph))
        for scc in sccs:
            if len(scc) > 1:
                branch = sorted(scc)
                independent_branches.append(branch)

    deduped: list[list[str]] = []
    seen: set[frozenset[str]] = set()
    for branch in independent_branches:
        key = frozenset(branch)
        if key not in seen:
            seen.add(key)
            deduped.append(branch)
    return deduped


def _parallel_levels(graph: nx.DiGraph) -> list[set[str]]:
    levels: list[set[str]] = []
    assigned: set[str] = set()
    roots = {n for n in graph.nodes if graph.in_degree(n) == 0}
    current_level = roots

    while current_level:
        levels.append(current_level)
        assigned.update(current_level)
        next_level: set[str] = set()
        for node in current_level:
            for successor in graph.successors(node):
                if successor not in assigned:
                    predecessors = set(graph.predecessors(successor))
                    if predecessors.issubset(assigned):
                        next_level.add(successor)
        current_level = next_level

    return levels


# ------------------------------------------------------------------
# clean_dependency_cycles
# ------------------------------------------------------------------

def clean_dependency_cycles(
    graph: SoftwareGraph,
    graph_index: GraphIndex,
) -> SoftwareGraph:
    working = copy.deepcopy(graph)

    for layer_graph in working.layers.values():
        nx_graph = nx.DiGraph()
        for node in layer_graph.nodes:
            nx_graph.add_node(node.id)
        for edge in layer_graph.edges:
            nx_graph.add_edge(edge.source, edge.target)

        sccs = list(nx.strongly_connected_components(nx_graph))
        edges_to_remove: set[tuple[str, str]] = set()

        for scc in sccs:
            if len(scc) <= 1:
                continue
            subgraph = nx_graph.subgraph(scc)
            cycle_edges = list(nx.simple_cycles(subgraph))
            for cycle in cycle_edges:
                worst_edge = _select_cycle_break_edge(cycle, layer_graph)
                if worst_edge is not None:
                    edges_to_remove.add(worst_edge)

        surviving_edges = [
            e for e in layer_graph.edges
            if (e.source, e.target) not in edges_to_remove
        ]
        working.layers[layer_graph.layer] = _rebuild_graph(
            layer_graph, layer_graph.nodes, surviving_edges,
        )

    return working


def _select_cycle_break_edge(
    cycle: list[str],
    layer_graph: SGIRGraph,
) -> tuple[str, str] | None:
    node_map = _node_map(layer_graph)
    worst_complexity = -1
    worst_edge: tuple[str, str] | None = None

    for i in range(len(cycle)):
        src = cycle[i]
        tgt = cycle[(i + 1) % len(cycle)]
        node = node_map.get(src)
        if node is None:
            continue
        complexity_val = {
            "O(1)": 0, "O(log n)": 1, "O(n)": 2, "O(n log n)": 3,
            "O(n^2)": 4, "O(n^3)": 5, "O(2^n)": 6, "unknown": 7,
        }.get(node.complexity.value, 7)
        if complexity_val > worst_complexity:
            worst_complexity = complexity_val
            worst_edge = (src, tgt)

    return worst_edge


# ------------------------------------------------------------------
# reduce_complexity
# ------------------------------------------------------------------

COMPLEXITY_SPLIT_THRESHOLD = {"O(n^3)", "O(2^n)"}


def reduce_complexity(
    graph: SoftwareGraph,
    graph_index: GraphIndex,
) -> SoftwareGraph:
    working = copy.deepcopy(graph)

    for layer_graph in working.layers.values():
        new_nodes: list[SGIRNode] = []
        new_edges: list[SGIREdge] = list(layer_graph.edges)
        splits: dict[str, list[str]] = {}

        for node in layer_graph.nodes:
            if node.complexity.value not in COMPLEXITY_SPLIT_THRESHOLD:
                new_nodes.append(node)
                continue

            parts = _split_node(node)
            splits[node.id] = [p.id for p in parts]
            new_nodes.extend(parts)

        if not splits:
            continue

        for i, edge in enumerate(new_edges):
            if edge.source in splits:
                new_edges[i] = SGIREdge(
                    source=splits[edge.source][0],
                    target=edge.target,
                    edge_type=edge.edge_type,
                    weight=edge.weight,
                    label=edge.label,
                )
            if edge.target in splits:
                new_edges[i] = SGIREdge(
                    source=new_edges[i].source,
                    target=splits[edge.target][-1],
                    edge_type=edge.edge_type,
                    weight=edge.weight,
                    label=edge.label,
                )

        for _old_id, part_ids in splits.items():
            for j in range(len(part_ids) - 1):
                new_edges.append(SGIREdge(
                    source=part_ids[j],
                    target=part_ids[j + 1],
                    edge_type=EdgeType.CONTROL,
                    label="split_chain",
                ))

        working.layers[layer_graph.layer] = _rebuild_graph(
            layer_graph, new_nodes, new_edges,
        )

    return working


def _split_node(node: SGIRNode, num_parts: int = 2) -> list[SGIRNode]:
    parts: list[SGIRNode] = []
    for i in range(num_parts):
        part_id = f"{node.id}__part{i}"
        parts.append(SGIRNode(
            id=part_id,
            name=f"{node.name}_part{i}",
            purpose=node.purpose,
            node_type=node.node_type,
            language=node.language,
            source_location=node.source_location,
            inputs=node.inputs if i == 0 else [f"{node.id}__part{i - 1}"],
            outputs=node.outputs if i == num_parts - 1 else [part_id],
            preconditions=node.preconditions if i == 0 else [],
            postconditions=node.postconditions if i == num_parts - 1 else [],
            side_effects=node.side_effects,
            external_dependencies=node.external_dependencies,
            complexity=ComplexityEstimate.LINEAR,
            failure_modes=node.failure_modes,
            security_boundary=node.security_boundary,
            ownership=node.ownership,
            test_coverage=node.test_coverage,
            documentation=node.documentation,
        ))
    return parts
