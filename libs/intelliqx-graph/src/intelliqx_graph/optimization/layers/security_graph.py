from __future__ import annotations

from typing import Any

from intelliqx_graph.layers import LayerBuilder
from intelliqx_graph.models import (
    EdgeType,
    GraphLayer,
    NodeType,
    SecurityBoundary,
    SGIREdge,
    SGIRGraph,
    SGIRNode,
    SourceLocation,
)


def make_node_id(file_path: str, name: str) -> str:
    return f"{file_path}::{name}"


_AUTH_PATTERNS = {
    "authenticate",
    "authorization",
    "auth",
    "login",
    "logout",
    "token",
    "jwt",
    "oauth",
    "session",
    "permission",
    "role",
    "access_control",
    "csrf",
    "cors",
    "sanitize",
    "escape",
    "validate",
    "hash",
    "encrypt",
    "decrypt",
    "sign",
    "verify",
    "secret",
    "credential",
    "api_key",
    "apikey",
    "password",
    "passwd",
}

_SENSITIVE_DATA_PATTERNS = {
    "password",
    "secret",
    "token",
    "key",
    "credential",
    "private",
    "ssn",
    "credit_card",
    "email",
    "pii",
    "phi",
}


class SecurityGraphBuilder(LayerBuilder):
    @property
    def layer(self) -> GraphLayer:
        return GraphLayer.SECURITY

    def build(self, parsed_data: dict[str, Any], existing: SGIRGraph | None = None) -> SGIRGraph:
        entities = parsed_data.get("entities", [])
        nodes: list[SGIRNode] = []
        edges: list[SGIREdge] = []
        node_ids: set[str] = set()

        security_nodes: dict[str, str] = {}

        for entity in entities:
            if entity.entity_type not in {"function", "method", "class"}:
                continue

            boundary = classify_security_boundary(entity)
            auth_ops = detect_auth_patterns(entity)

            nid = make_node_id(entity.file_path, entity.name)
            if nid not in node_ids:
                node_ids.add(nid)
                nodes.append(SGIRNode(
                    id=nid,
                    name=entity.name,
                    purpose=entity.docstring or "",
                    node_type=NodeType.METHOD if entity.entity_type == "method" else (
                        NodeType.CLASS if entity.entity_type == "class" else NodeType.FUNCTION
                    ),
                    language=entity.language,
                    source_location=SourceLocation(
                        file_path=entity.file_path,
                        line_start=entity.line_start,
                        line_end=entity.line_end,
                    ),
                    security_boundary=boundary,
                    side_effects=auth_ops,
                ))

            for pattern in auth_ops:
                sec_id = f"security::{pattern}"
                if sec_id not in node_ids:
                    node_ids.add(sec_id)
                    security_nodes[pattern] = sec_id
                    nodes.append(SGIRNode(
                        id=sec_id,
                        name=pattern,
                        node_type=NodeType.MIDDLEWARE,
                        security_boundary=SecurityBoundary.AUTHENTICATED,
                        purpose=f"Security concern: {pattern}",
                    ))

                edges.append(SGIREdge(
                    source=nid,
                    target=sec_id,
                    edge_type=EdgeType.EVENT,
                    label=pattern,
                ))

            for ref in entity.references:
                if is_sensitive_data(ref):
                    sens_id = f"sensitive::{ref}"
                    if sens_id not in node_ids:
                        node_ids.add(sens_id)
                        nodes.append(SGIRNode(
                            id=sens_id,
                            name=ref,
                            node_type=NodeType.DATAMODEL,
                            security_boundary=SecurityBoundary.INTERNAL,
                            purpose=f"Sensitive data: {ref}",
                        ))

                    edges.append(SGIREdge(
                        source=nid,
                        target=sens_id,
                        edge_type=EdgeType.DATA,
                        label=f"accesses:{ref}",
                    ))

        metadata: dict[str, Any] = {}
        if existing:
            metadata = existing.metadata

        return SGIRGraph(
            layer=GraphLayer.SECURITY,
            nodes=nodes,
            edges=edges,
            metadata=metadata,
        )


def classify_security_boundary(entity: Any) -> SecurityBoundary:
    all_names = entity.calls + entity.references + entity.decorators
    all_text = " ".join(all_names).lower()

    if any(p in all_text for p in {"admin", "superuser", "root"}):
        return SecurityBoundary.ADMIN
    if any(p in all_text for p in _AUTH_PATTERNS):
        return SecurityBoundary.AUTHENTICATED
    if any(p in all_text for p in {"internal", "private"}):
        return SecurityBoundary.INTERNAL
    if any(p in all_text for p in {"external", "public", "api"}):
        return SecurityBoundary.EXTERNAL
    return SecurityBoundary.NONE


def detect_auth_patterns(entity: Any) -> list[str]:
    found: list[str] = []
    all_names = entity.calls + entity.references + entity.decorators
    for name in all_names:
        name_lower = name.lower()
        for pattern in _AUTH_PATTERNS:
            if pattern in name_lower:
                if pattern not in found:
                    found.append(pattern)
                break
    return found


def is_sensitive_data(name: str) -> bool:
    name_lower = name.lower()
    return any(p in name_lower for p in _SENSITIVE_DATA_PATTERNS)
