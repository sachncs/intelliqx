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


LIFECYCLE_DECORATORS = {
    "init",
    "__init__",
    "__post_init__",
    "__enter__",
    "__exit__",
    "__del__",
    "__new__",
    "setup",
    "teardown",
    "before_connect",
    "after_connect",
    "on_startup",
    "on_shutdown",
}

EVENT_DECORATORS = {"on", "event", "handler", "listener", "subscribe", "signal", "callback"}


class StateTransitionBuilder(LayerBuilder):
    @property
    def layer(self) -> GraphLayer:
        return GraphLayer.STATE_TRANSITION

    def build(self, parsed_data: dict[str, Any], existing: SGIRGraph | None = None) -> SGIRGraph:
        entities = parsed_data.get("entities", [])
        nodes: list[SGIRNode] = []
        edges: list[SGIREdge] = []
        node_ids: set[str] = set()
        class_methods: dict[str, list[Any]] = {}

        for entity in entities:
            if entity.entity_type == "class":
                nid = make_node_id(entity.file_path, entity.name)
                if nid not in node_ids:
                    node_ids.add(nid)
                    nodes.append(
                        SGIRNode(
                            id=nid,
                            name=entity.name,
                            purpose=entity.docstring or "",
                            node_type=NodeType.CLASS,
                            language=entity.language,
                            source_location=SourceLocation(
                                file_path=entity.file_path,
                                line_start=entity.line_start,
                                line_end=entity.line_end,
                            ),
                            preconditions=[b for b in entity.bases],
                        )
                    )

            if entity.entity_type == "method" and entity.parent:
                class_methods.setdefault(entity.parent, []).append(entity)

        for class_name, methods in class_methods.items():
            lifecycle_methods = []
            event_methods = []
            other_methods = []

            for method in methods:
                method_decorators = {d.lower() for d in method.decorators}
                method_names = {method.name}

                if method_names & LIFECYCLE_DECORATORS or method_decorators & LIFECYCLE_DECORATORS:
                    lifecycle_methods.append(method)
                elif method_names & EVENT_DECORATORS or method_decorators & EVENT_DECORATORS:
                    event_methods.append(method)
                else:
                    other_methods.append(method)

            for method in lifecycle_methods:
                nid = make_node_id(method.file_path, method.name)
                if nid not in node_ids:
                    node_ids.add(nid)
                    nodes.append(
                        SGIRNode(
                            id=nid,
                            name=method.name,
                            purpose=method.docstring or "",
                            node_type=NodeType.METHOD,
                            language=method.language,
                            source_location=SourceLocation(
                                file_path=method.file_path,
                                line_start=method.line_start,
                                line_end=method.line_end,
                            ),
                            inputs=method.parameters,
                            outputs=[method.return_type] if method.return_type else [],
                        )
                    )

                class_id = make_node_id(method.file_path, class_name)
                if class_id in node_ids:
                    edges.append(
                        SGIREdge(
                            source=class_id,
                            target=nid,
                            edge_type=EdgeType.STATE_TRANSITION,
                            label=method.name,
                        )
                    )

            for i, method in enumerate(lifecycle_methods):
                if i > 0:
                    prev_id = make_node_id(
                        lifecycle_methods[i - 1].file_path, lifecycle_methods[i - 1].name
                    )
                    curr_id = make_node_id(method.file_path, method.name)
                    if prev_id in node_ids and curr_id in node_ids:
                        edges.append(
                            SGIREdge(
                                source=prev_id,
                                target=curr_id,
                                edge_type=EdgeType.STATE_TRANSITION,
                                label="next",
                            )
                        )

            for method in event_methods:
                nid = make_node_id(method.file_path, method.name)
                if nid not in node_ids:
                    node_ids.add(nid)
                    nodes.append(
                        SGIRNode(
                            id=nid,
                            name=method.name,
                            purpose=method.docstring or "",
                            node_type=NodeType.EVENT_HANDLER,
                            language=method.language,
                            source_location=SourceLocation(
                                file_path=method.file_path,
                                line_start=method.line_start,
                                line_end=method.line_end,
                            ),
                            inputs=method.parameters,
                            outputs=[method.return_type] if method.return_type else [],
                        )
                    )

                for called in method.calls:
                    target_ids = resolve_ids(called, entities, node_ids)
                    for target_id in target_ids:
                        if target_id != nid:
                            edges.append(
                                SGIREdge(
                                    source=nid,
                                    target=target_id,
                                    edge_type=EdgeType.EVENT,
                                    label=called,
                                )
                            )

        for entity in entities:
            if entity.entity_type == "class" and entity.bases:
                nid = make_node_id(entity.file_path, entity.name)
                for base in entity.bases:
                    base_id = find_class_id(base, entities, node_ids)
                    if base_id and nid in node_ids:
                        edges.append(
                            SGIREdge(
                                source=nid, target=base_id, edge_type=EdgeType.INHERIT, label=base
                            )
                        )

        metadata: dict[str, Any] = {}
        if existing:
            metadata = existing.metadata

        return SGIRGraph(
            layer=GraphLayer.STATE_TRANSITION, nodes=nodes, edges=edges, metadata=metadata
        )


def resolve_ids(name: str, entities: list[Any], node_ids: set[str]) -> list[str]:
    results: list[str] = []
    for entity in entities:
        if entity.name == name:
            nid = make_node_id(entity.file_path, entity.name)
            if nid in node_ids:
                results.append(nid)
    return results


def find_class_id(name: str, entities: list[Any], node_ids: set[str]) -> str | None:
    for entity in entities:
        if entity.entity_type == "class" and entity.name == name:
            nid = make_node_id(entity.file_path, entity.name)
            if nid in node_ids:
                return nid
    return None
