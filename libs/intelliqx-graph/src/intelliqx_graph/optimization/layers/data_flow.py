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


class DataFlowBuilder(LayerBuilder):
    @property
    def layer(self) -> GraphLayer:
        return GraphLayer.DATA_FLOW

    def build(self, parsed_data: dict[str, Any], existing: SGIRGraph | None = None) -> SGIRGraph:
        entities = parsed_data.get("entities", [])
        nodes: list[SGIRNode] = []
        edges: list[SGIREdge] = []
        node_ids: set[str] = set()
        name_to_ids: dict[str, list[str]] = {}

        for entity in entities:
            if entity.entity_type not in {"function", "method"}:
                continue

            nid = make_node_id(entity.file_path, entity.name)
            if nid in node_ids:
                continue
            node_ids.add(nid)
            name_to_ids.setdefault(entity.name, []).append(nid)

            nodes.append(
                SGIRNode(
                    id=nid,
                    name=entity.name,
                    purpose=entity.docstring or "",
                    node_type=(
                        NodeType.METHOD if entity.entity_type == "method" else NodeType.FUNCTION
                    ),
                    language=entity.language,
                    source_location=SourceLocation(
                        file_path=entity.file_path,
                        line_start=entity.line_start,
                        line_end=entity.line_end,
                    ),
                    inputs=entity.parameters,
                    outputs=[entity.return_type] if entity.return_type else [],
                    complexity=entity.complexity,
                )
            )

        for entity in entities:
            if entity.entity_type not in {"function", "method"}:
                continue

            source_id = make_node_id(entity.file_path, entity.name)
            for ref in entity.references:
                if ref in name_to_ids:
                    for target_id in name_to_ids[ref]:
                        if target_id != source_id:
                            edges.append(
                                SGIREdge(
                                    source=source_id,
                                    target=target_id,
                                    edge_type=EdgeType.DATA,
                                    label=ref,
                                )
                            )

        metadata: dict[str, Any] = {}
        if existing:
            metadata = existing.metadata

        return SGIRGraph(layer=GraphLayer.DATA_FLOW, nodes=nodes, edges=edges, metadata=metadata)
