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


CONFIG_FILE_PATTERNS = {
    "config",
    "settings",
    "env",
    "yaml",
    "yml",
    "toml",
    "ini",
    "json",
    "properties",
}


class DeploymentGraphBuilder(LayerBuilder):
    @property
    def layer(self) -> GraphLayer:
        return GraphLayer.DEPLOYMENT

    def build(self, parsed_data: dict[str, Any], existing: SGIRGraph | None = None) -> SGIRGraph:
        entities = parsed_data.get("entities", [])
        repository = parsed_data.get("repository")
        nodes: list[SGIRNode] = []
        edges: list[SGIREdge] = []
        node_ids: set[str] = set()

        if repository:
            repo_id = f"deploy::{repository.name}"
            node_ids.add(repo_id)
            nodes.append(
                SGIRNode(
                    id=repo_id,
                    name=repository.name,
                    node_type=NodeType.SERVICE,
                    language=", ".join(repository.languages),
                    external_dependencies=repository.frameworks,
                )
            )

            for build_system in repository.build_systems:
                build_id = make_node_id("build", build_system)
                if build_id not in node_ids:
                    node_ids.add(build_id)
                    nodes.append(
                        SGIRNode(
                            id=build_id,
                            name=build_system,
                            node_type=NodeType.CONFIG,
                            purpose=f"Build system: {build_system}",
                        )
                    )
                    edges.append(
                        SGIREdge(
                            source=repo_id,
                            target=build_id,
                            edge_type=EdgeType.DEPENDENCY,
                            label="builds_with",
                        )
                    )

        config_entities = [e for e in entities if is_config_entity(e)]
        for entity in config_entities:
            nid = make_node_id("config", entity.name)
            if nid not in node_ids:
                node_ids.add(nid)
                nodes.append(
                    SGIRNode(
                        id=nid,
                        name=entity.name,
                        node_type=NodeType.CONFIG,
                        language=entity.language,
                        source_location=SourceLocation(
                            file_path=entity.file_path,
                            line_start=entity.line_start,
                            line_end=entity.line_end,
                        ),
                        purpose=entity.docstring or "",
                    )
                )

                if repository:
                    repo_id = f"deploy::{repository.name}"
                    if repo_id in node_ids:
                        edges.append(
                            SGIREdge(
                                source=repo_id,
                                target=nid,
                                edge_type=EdgeType.DEPENDENCY,
                                label="configures",
                            )
                        )

        for entity in entities:
            if entity.entity_type in {"function", "method"}:
                decorators_lower = [d.lower() for d in entity.decorators]
                is_deployable = any(
                    any(p in d for p in {"route", "app", "handler", "entry", "main"})
                    for d in decorators_lower
                )
                if is_deployable:
                    nid = make_node_id(entity.file_path, entity.name)
                    if nid not in node_ids:
                        node_ids.add(nid)
                        nodes.append(
                            SGIRNode(
                                id=nid,
                                name=entity.name,
                                node_type=NodeType.ENDPOINT,
                                language=entity.language,
                                source_location=SourceLocation(
                                    file_path=entity.file_path,
                                    line_start=entity.line_start,
                                    line_end=entity.line_end,
                                ),
                            )
                        )

                        if repository:
                            repo_id = f"deploy::{repository.name}"
                            if repo_id in node_ids:
                                edges.append(
                                    SGIREdge(
                                        source=repo_id,
                                        target=nid,
                                        edge_type=EdgeType.DEPENDENCY,
                                        label="exposes",
                                    )
                                )

        metadata: dict[str, Any] = {}
        if existing:
            metadata = existing.metadata

        return SGIRGraph(layer=GraphLayer.DEPLOYMENT, nodes=nodes, edges=edges, metadata=metadata)


def is_config_entity(entity: Any) -> bool:
    name_lower = entity.name.lower()
    return any(p in name_lower for p in CONFIG_FILE_PATTERNS)
