from __future__ import annotations

from typing import Any

from intelliqx_graph.layers import LayerBuilder
from intelliqx_graph.models import (
    EdgeType,
    GraphLayer,
    NodeType,
    SGIREdge,
    SGIRGraph,
    SGIRNode,
    SourceLocation,
)


def make_node_id(file_path: str, name: str) -> str:
    return f"{file_path}::{name}"


class CallGraphBuilder(LayerBuilder):
    @property
    def layer(self) -> GraphLayer:
        return GraphLayer.CALL

    def build(self, parsed_data: dict[str, Any], existing: SGIRGraph | None = None) -> SGIRGraph:
        entities = parsed_data.get("entities", [])
        nodes: list[SGIRNode] = []
        edges: list[SGIREdge] = []
        node_ids: set[str] = set()

        callable_types = {"function", "method", "class"}

        for entity in entities:
            if entity.entity_type not in callable_types:
                continue

            nid = make_node_id(entity.file_path, entity.name)
            if nid in node_ids:
                continue
            node_ids.add(nid)

            node_type = NodeType.METHOD if entity.entity_type == "method" else (
                NodeType.CLASS if entity.entity_type == "class" else NodeType.FUNCTION
            )

            nodes.append(SGIRNode(
                id=nid,
                name=entity.name,
                purpose=entity.docstring or "",
                node_type=node_type,
                language=entity.language,
                source_location=SourceLocation(
                    file_path=entity.file_path,
                    line_start=entity.line_start,
                    line_end=entity.line_end,
                ),
                inputs=entity.parameters,
                outputs=[entity.return_type] if entity.return_type else [],
                complexity=entity.complexity,
            ))

        for entity in entities:
            if entity.entity_type not in callable_types:
                continue

            source_id = make_node_id(entity.file_path, entity.name)
            for call_name in entity.calls:
                target_id = find_call_target(call_name, entity, entities, node_ids)
                if target_id and target_id != source_id:
                    edges.append(SGIREdge(
                        source=source_id,
                        target=target_id,
                        edge_type=EdgeType.CALL,
                        label=call_name,
                    ))

        metadata: dict[str, Any] = {}
        if existing:
            metadata = existing.metadata

        return SGIRGraph(
            layer=GraphLayer.CALL,
            nodes=nodes,
            edges=edges,
            metadata=metadata,
        )


def find_call_target(
    call_name: str,
    caller: Any,
    entities: list[Any],
    node_ids: set[str],
) -> str | None:
    for entity in entities:
        if entity.name == call_name:
            nid = make_node_id(entity.file_path, entity.name)
            if nid in node_ids:
                return nid
    parent_id = make_node_id(caller.file_path, f"{caller.parent}.{call_name}") if caller.parent else None
    if parent_id and parent_id in node_ids:
        return parent_id
    return None
