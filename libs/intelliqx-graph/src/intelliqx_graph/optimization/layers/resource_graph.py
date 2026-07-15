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


def _make_node_id(file_path: str, name: str) -> str:
    return f"{file_path}::{name}"


_IO_PATTERNS = {
    "open",
    "read",
    "write",
    "connect",
    "send",
    "recv",
    "fetch",
    "request",
    "urlopen",
    "socket",
    "database",
    "query",
    "execute",
    "cursor",
    "connection",
    "session",
    "cache",
    "redis",
    "mq",
    "queue",
    "publish",
    "consume",
    "subscribe",
}

_EXTERNAL_CALL_PATTERNS = {
    "requests",
    "httpx",
    "urllib",
    "aiohttp",
    "grpc",
    "websocket",
    "socket",
    "subprocess",
    "os.system",
}


class ResourceGraphBuilder(LayerBuilder):
    @property
    def layer(self) -> GraphLayer:
        return GraphLayer.RESOURCE

    def build(self, parsed_data: dict[str, Any], existing: SGIRGraph | None = None) -> SGIRGraph:
        entities = parsed_data.get("entities", [])
        nodes: list[SGIRNode] = []
        edges: list[SGIREdge] = []
        node_ids: set[str] = set()

        resource_nodes: dict[str, str] = {}

        for entity in entities:
            if entity.entity_type not in {"function", "method"}:
                continue

            nid = _make_node_id(entity.file_path, entity.name)
            if nid in node_ids:
                continue
            node_ids.add(nid)

            side_effects = _detect_io_operations(entity)

            nodes.append(SGIRNode(
                id=nid,
                name=entity.name,
                purpose=entity.docstring or "",
                node_type=NodeType.METHOD if entity.entity_type == "method" else NodeType.FUNCTION,
                language=entity.language,
                source_location=SourceLocation(
                    file_path=entity.file_path,
                    line_start=entity.line_start,
                    line_end=entity.line_end,
                ),
                inputs=entity.parameters,
                outputs=[entity.return_type] if entity.return_type else [],
                side_effects=side_effects,
                resource_usage=_build_resource_usage(entity),
            ))

            for resource_name in side_effects:
                res_id = f"resource::{resource_name}"
                if res_id not in node_ids:
                    node_ids.add(res_id)
                    resource_nodes[resource_name] = res_id
                    nodes.append(SGIRNode(
                        id=res_id,
                        name=resource_name,
                        node_type=NodeType.SERVICE,
                        resource_usage={"type": _classify_resource(resource_name)},
                    ))

                edges.append(SGIREdge(
                    source=nid,
                    target=res_id,
                    edge_type=EdgeType.NETWORK if _is_external(resource_name) else EdgeType.DATABASE,
                    label=resource_name,
                ))

        metadata: dict[str, Any] = {}
        if existing:
            metadata = existing.metadata

        return SGIRGraph(
            layer=GraphLayer.RESOURCE,
            nodes=nodes,
            edges=edges,
            metadata=metadata,
        )


def _detect_io_operations(entity: Any) -> list[str]:
    effects: list[str] = []
    all_names = entity.calls + entity.references
    for name in all_names:
        name_lower = name.lower()
        for pattern in _IO_PATTERNS:
            if pattern in name_lower:
                if name not in effects:
                    effects.append(name)
                break
    return effects


def _build_resource_usage(entity: Any) -> dict[str, Any]:
    usage: dict[str, Any] = {}
    io_ops = _detect_io_operations(entity)
    if io_ops:
        usage["io_operations"] = io_ops
    if entity.is_async:
        usage["async"] = True
    return usage


def _classify_resource(name: str) -> str:
    name_lower = name.lower()
    if any(p in name_lower for p in {"database", "query", "cursor", "connection", "execute"}):
        return "database"
    if any(p in name_lower for p in {"cache", "redis", "memcache"}):
        return "cache"
    if any(p in name_lower for p in {"queue", "mq", "publish", "consume", "subscribe"}):
        return "message_queue"
    if any(p in name_lower for p in {"requests", "httpx", "urllib", "aiohttp", "fetch", "socket"}):
        return "http"
    return "file"


def _is_external(name: str) -> bool:
    name_lower = name.lower()
    return any(p in name_lower for p in _EXTERNAL_CALL_PATTERNS)
