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


_CONTROL_FLOW_DECORATORS = {
    "app.route",
    "route",
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "before_request",
    "after_request",
    "errorhandler",
    "middleware",
}


class ControlFlowBuilder(LayerBuilder):
    @property
    def layer(self) -> GraphLayer:
        return GraphLayer.CONTROL_FLOW

    def build(self, parsed_data: dict[str, Any], existing: SGIRGraph | None = None) -> SGIRGraph:
        entities = parsed_data.get("entities", [])
        nodes: list[SGIRNode] = []
        edges: list[SGIREdge] = []
        node_ids: set[str] = set()

        for entity in entities:
            if entity.entity_type not in {"function", "method", "class"}:
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
                side_effects=detect_side_effects(entity),
            ))

        for entity in entities:
            if entity.entity_type == "class":
                class_id = make_node_id(entity.file_path, entity.name)
                for child in entities:
                    if child.parent == entity.name and child.entity_type == "method":
                        method_id = make_node_id(child.file_path, child.name)
                        if class_id in node_ids and method_id in node_ids:
                            edges.append(SGIREdge(
                                source=class_id,
                                target=method_id,
                                edge_type=EdgeType.CONTROL,
                                label="contains",
                            ))

        for entity in entities:
            if entity.entity_type not in {"function", "method"}:
                continue
            if is_entry_point(entity):
                nid = make_node_id(entity.file_path, entity.name)
                if nid in node_ids:
                    for call_name in entity.calls:
                        target_ids = resolve_ids(call_name, entities, node_ids)
                        for target_id in target_ids:
                            if target_id != nid:
                                edges.append(SGIREdge(
                                    source=nid,
                                    target=target_id,
                                    edge_type=EdgeType.CONTROL,
                                    label=call_name,
                                ))

        metadata: dict[str, Any] = {}
        if existing:
            metadata = existing.metadata

        return SGIRGraph(
            layer=GraphLayer.CONTROL_FLOW,
            nodes=nodes,
            edges=edges,
            metadata=metadata,
        )


def detect_side_effects(entity: Any) -> list[str]:
    effects: list[str] = []
    if entity.is_async:
        effects.append("async")
    if entity.is_generator:
        effects.append("generator")
    for decorator in entity.decorators:
        low = decorator.lower()
        for pattern in _CONTROL_FLOW_DECORATORS:
            if pattern in low:
                effects.append(f"route:{decorator}")
                break
    return effects


def is_entry_point(entity: Any) -> bool:
    for decorator in entity.decorators:
        low = decorator.lower()
        for pattern in _CONTROL_FLOW_DECORATORS:
            if pattern in low:
                return True
    return False


def resolve_ids(name: str, entities: list[Any], node_ids: set[str]) -> list[str]:
    results: list[str] = []
    for entity in entities:
        if entity.name == name:
            nid = make_node_id(entity.file_path, entity.name)
            if nid in node_ids:
                results.append(nid)
    return results
