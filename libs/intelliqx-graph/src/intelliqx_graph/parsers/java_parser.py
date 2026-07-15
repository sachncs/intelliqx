"""Java tree-sitter parser.

Uses ``tree_sitter_languages`` to parse Java source files into
``ParsedEntity`` objects. Extracts classes, methods, constructors,
imports, interfaces, and basic complexity estimates.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter_languages import get_parser

from intelliqx_graph.parsers import BaseParser, ParsedEntity


def node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def estimate_complexity(node) -> str:
    complexity = 1
    stack = [node]
    while stack:
        current = stack.pop()
        type_name = current.type
        if type_name in ("if_statement", "while_statement", "for_statement", "switch_expression", "catch_clause") or type_name == "case_clause":
            complexity += 1
        elif type_name == "binary_expression":
            op = current.child_by_field_name("operator")
            if op and op.type in ("&&", "||"):
                complexity += 1
        for child in current.children:
            stack.append(child)

    if complexity <= 1:
        return "O(1)"
    elif complexity <= 3:
        return "O(n)"
    elif complexity <= 6:
        return "O(n log n)"
    elif complexity <= 10:
        return "O(n^2)"
    else:
        return "O(n^3)"


class JavaParser(BaseParser):
    """Java tree-sitter parser."""

    @property
    def language(self) -> str:
        return "java"

    def supported_extensions(self) -> list[str]:
        return [".java"]

    def parse_file(self, file_path: Path) -> list[ParsedEntity]:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        source_bytes = bytes(source, "utf-8")

        try:
            parser = get_parser("java")
            tree = parser.parse(source_bytes)
        except Exception:
            return []

        entities: list[ParsedEntity] = []
        file_str = str(file_path)

        self._walk(tree.root_node, source_bytes, file_str, entities, parent=None)
        return entities

    def _walk(self, node, source_bytes: bytes, file_str: str, entities: list[ParsedEntity], parent: str | None):
        for child in node.children:
            ctype = child.type

            if ctype == "class_declaration":
                class_entity = self._parse_class(child, source_bytes, file_str, parent)
                entities.append(class_entity)
                self._walk(child, source_bytes, file_str, entities, parent=class_entity.name)

            elif ctype == "interface_declaration":
                class_entity = self._parse_interface(child, source_bytes, file_str, parent)
                entities.append(class_entity)
                self._walk(child, source_bytes, file_str, entities, parent=class_entity.name)

            elif ctype == "enum_declaration":
                class_entity = self._parse_class(child, source_bytes, file_str, parent)
                entities.append(class_entity)

            elif ctype == "method_declaration":
                entities.append(self._parse_method(child, source_bytes, file_str, parent))

            elif ctype == "constructor_declaration":
                entities.append(self._parse_constructor(child, source_bytes, file_str, parent))

            elif ctype == "import_declaration":
                entities.append(self._parse_import(child, source_bytes, file_str))

    def _parse_class(self, node, source_bytes: bytes, file_str: str, parent: str | None) -> ParsedEntity:
        name_node = node.child_by_field_name("name")
        name = node_text(name_node, source_bytes) if name_node else "anonymous"

        bases: list[str] = []
        superclass = node.child_by_field_name("superclass")
        if superclass:
            bases.append(node_text(superclass, source_bytes))
        interfaces = node.child_by_field_name("interfaces")
        if interfaces:
            for child in interfaces.children:
                if child.type == "type_identifier":
                    bases.append(node_text(child, source_bytes))

        annotations = self._parse_annotations(node, source_bytes)

        return ParsedEntity(
            name=name,
            entity_type="class",
            file_path=file_str,
            line_start=node.start_point[0],
            line_end=node.end_point[0],
            language="java",
            parent=parent,
            bases=bases,
            decorators=annotations,
        )

    def _parse_interface(self, node, source_bytes: bytes, file_str: str, parent: str | None) -> ParsedEntity:
        name_node = node.child_by_field_name("name")
        name = node_text(name_node, source_bytes) if name_node else "anonymous"

        bases: list[str] = []
        interfaces = node.child_by_field_name("interfaces")
        if interfaces:
            for child in interfaces.children:
                if child.type == "type_identifier":
                    bases.append(node_text(child, source_bytes))

        return ParsedEntity(
            name=name,
            entity_type="class",
            file_path=file_str,
            line_start=node.start_point[0],
            line_end=node.end_point[0],
            language="java",
            parent=parent,
            bases=bases,
        )

    def _parse_method(self, node, source_bytes: bytes, file_str: str, parent: str | None) -> ParsedEntity:
        name_node = node.child_by_field_name("name")
        name = node_text(name_node, source_bytes) if name_node else "anonymous"
        params_node = node.child_by_field_name("parameters")
        params = self._parse_parameters(params_node, source_bytes) if params_node else []
        return_type_node = node.child_by_field_name("type")
        return_type = node_text(return_type_node, source_bytes) if return_type_node else None

        modifiers = self._parse_modifiers(node, source_bytes)
        is_static = "static" in modifiers
        is_abstract = "abstract" in modifiers

        return ParsedEntity(
            name=name,
            entity_type="method",
            file_path=file_str,
            line_start=node.start_point[0],
            line_end=node.end_point[0],
            language="java",
            parent=parent,
            parameters=params,
            return_type=return_type,
            is_static=is_static,
            is_abstract=is_abstract,
            complexity=estimate_complexity(node),
        )

    def _parse_constructor(self, node, source_bytes: bytes, file_str: str, parent: str | None) -> ParsedEntity:
        name_node = node.child_by_field_name("name")
        name = node_text(name_node, source_bytes) if name_node else "anonymous"
        params_node = node.child_by_field_name("parameters")
        params = self._parse_parameters(params_node, source_bytes) if params_node else []

        return ParsedEntity(
            name=name,
            entity_type="method",
            file_path=file_str,
            line_start=node.start_point[0],
            line_end=node.end_point[0],
            language="java",
            parent=parent,
            parameters=params,
            complexity=estimate_complexity(node),
        )

    def _parse_import(self, node, source_bytes: bytes, file_str: str) -> ParsedEntity:
        source_text = node_text(node, source_bytes)
        import_source = source_text.replace("import ", "").replace(";", "").strip()
        is_from_import = ".*" not in import_source and import_source.count(".") > 1

        parts = import_source.rsplit(".", 1)
        import_name = parts[-1] if len(parts) > 1 else import_source

        return ParsedEntity(
            name=f"from_{import_source}",
            entity_type="import",
            file_path=file_str,
            line_start=node.start_point[0],
            line_end=node.end_point[0],
            language="java",
            import_source=import_source,
            import_names=[import_name],
            is_from_import=is_from_import,
        )

    def _parse_parameters(self, params_node, source_bytes: bytes) -> list[str]:
        params: list[str] = []
        for child in params_node.children:
            if child.type == "formal_parameter":
                type_node = child.child_by_field_name("type")
                name_node = child.child_by_field_name("name")
                type_text = node_text(type_node, source_bytes) if type_node else ""
                name_text = node_text(name_node, source_bytes) if name_node else ""
                if type_text and name_text:
                    params.append(f"{type_text} {name_text}")
            elif child.type == "spread_parameter":
                params.append(f"...{node_text(child, source_bytes)}")
        return params

    def _parse_modifiers(self, node, source_bytes: bytes) -> list[str]:
        modifiers: list[str] = []
        for child in node.children:
            if child.type in ("public", "private", "protected", "static", "final", "abstract", "synchronized", "native", "strictfp"):
                modifiers.append(child.type)
            elif child.type == "modifiers":
                for mod in child.children:
                    modifiers.append(mod.type)
        return modifiers

    def _parse_annotations(self, node, source_bytes: bytes) -> list[str]:
        annotations: list[str] = []
        for child in node.children:
            if child.type == "annotation":
                name_node = child.child_by_field_name("name")
                if name_node:
                    annotations.append(f"@{node_text(name_node, source_bytes)}")
        return annotations
