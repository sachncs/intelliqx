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


def make_node_id(prefix: str, name: str) -> str:
    return f"{prefix}::{name}"


class DependencyGraphBuilder(LayerBuilder):
    @property
    def layer(self) -> GraphLayer:
        return GraphLayer.DEPENDENCY

    def build(self, parsed_data: dict[str, Any], existing: SGIRGraph | None = None) -> SGIRGraph:
        entities = parsed_data.get("entities", [])
        repository = parsed_data.get("repository")
        nodes: list[SGIRNode] = []
        edges: list[SGIREdge] = []
        node_ids: set[str] = set()

        file_module_map: dict[str, str] = {}
        for entity in entities:
            if entity.entity_type != "import":
                file_module_map.setdefault(entity.file_path, entity.file_path)

        module_nodes: dict[str, str] = {}

        for entity in entities:
            if entity.entity_type == "import":
                for imp_name in entity.import_names:
                    source_id = make_node_id("module", entity.file_path)
                    target_id = make_node_id("module", imp_name)

                    if source_id not in node_ids:
                        node_ids.add(source_id)
                        module_nodes[entity.file_path] = source_id
                        nodes.append(SGIRNode(
                            id=source_id,
                            name=entity.file_path,
                            node_type=NodeType.MODULE,
                            language=entity.language,
                            source_location=SourceLocation(
                                file_path=entity.file_path,
                                line_start=entity.line_start,
                                line_end=entity.line_end,
                            ),
                        ))

                    if target_id not in node_ids:
                        node_ids.add(target_id)
                        module_nodes[imp_name] = target_id
                        nodes.append(SGIRNode(
                            id=target_id,
                            name=imp_name,
                            node_type=NodeType.PACKAGE if "." in imp_name else NodeType.MODULE,
                            language=entity.language,
                        ))

                    edges.append(SGIREdge(
                        source=source_id,
                        target=target_id,
                        edge_type=EdgeType.IMPORT,
                        label=imp_name,
                    ))

        if repository:
            repo_id = f"repo::{repository.name}"
            if repo_id not in node_ids:
                node_ids.add(repo_id)
                nodes.append(SGIRNode(
                    id=repo_id,
                    name=repository.name,
                    node_type=NodeType.PACKAGE,
                    language=", ".join(repository.languages),
                    external_dependencies=repository.frameworks,
                ))

            for module_id in module_nodes.values():
                if module_id != repo_id:
                    edges.append(SGIREdge(
                        source=repo_id,
                        target=module_id,
                        edge_type=EdgeType.DEPENDENCY,
                    ))

        metadata: dict[str, Any] = {}
        if existing:
            metadata = existing.metadata

        return SGIRGraph(
            layer=GraphLayer.DEPENDENCY,
            nodes=nodes,
            edges=edges,
            metadata=metadata,
        )
