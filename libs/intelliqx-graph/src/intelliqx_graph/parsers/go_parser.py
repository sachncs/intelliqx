"""Go tree-sitter parser.

Uses ``tree_sitter_languages`` to parse Go source files into
``ParsedEntity`` objects. Extracts functions, methods, types,
imports, and basic complexity estimates.
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
        if type_name in ("if_statement", "for_statement", "type_switch_statement", "select_statement") or type_name == "case_clause":
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


class GoParser(BaseParser):
    """Go tree-sitter parser."""

    @property
    def language(self) -> str:
        return "go"

    def supported_extensions(self) -> list[str]:
        return [".go"]

    def parse_file(self, file_path: Path) -> list[ParsedEntity]:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        source_bytes = bytes(source, "utf-8")

        try:
            parser = get_parser("go")
            tree = parser.parse(source_bytes)
        except Exception:
            return []

        entities: list[ParsedEntity] = []
        file_str = str(file_path)

        self._walk(tree.root_node, source_bytes, file_str, entities)
        return entities

    def _walk(self, node, source_bytes: bytes, file_str: str, entities: list[ParsedEntity]):
        for child in node.children:
            ctype = child.type

            if ctype == "function_declaration":
                entities.append(self._parse_function(child, source_bytes, file_str, parent=None))

            elif ctype == "method_declaration":
                entities.append(self._parse_method(child, source_bytes, file_str))

            elif ctype == "type_declaration":
                for spec in child.children:
                    if spec.type == "type_spec":
                        name_node = spec.child_by_field_name("name")
                        name = node_text(name_node, source_bytes) if name_node else "anonymous"
                        type_node = spec.child_by_field_name("type")
                        entity_type = "class"
                        if (type_node and type_node.type == "interface_type") or (type_node and type_node.type == "struct_type"):
                            entity_type = "class"

                        bases: list[str] = []
                        if type_node and type_node.type == "struct_type":
                            for field in type_node.children:
                                if field.type == "field_declaration":
                                    field_type = field.child_by_field_name("type")
                                    if field_type:
                                        bases.append(node_text(field_type, source_bytes))

                        entities.append(ParsedEntity(
                            name=name,
                            entity_type=entity_type,
                            file_path=file_str,
                            line_start=spec.start_point[0],
                            line_end=spec.end_point[0],
                            language="go",
                            bases=bases,
                        ))

            elif ctype == "import_declaration":
                entities.extend(self._parse_import(child, source_bytes, file_str))

    def _parse_function(self, node, source_bytes: bytes, file_str: str, parent: str | None) -> ParsedEntity:
        name_node = node.child_by_field_name("name")
        name = node_text(name_node, source_bytes) if name_node else "anonymous"
        params_node = node.child_by_field_name("parameters")
        params = self._parse_parameters(params_node, source_bytes) if params_node else []
        result_node = node.child_by_field_name("result")
        return_type = node_text(result_node, source_bytes) if result_node else None

        return ParsedEntity(
            name=name,
            entity_type="function",
            file_path=file_str,
            line_start=node.start_point[0],
            line_end=node.end_point[0],
            language="go",
            parent=parent,
            parameters=params,
            return_type=return_type,
            complexity=estimate_complexity(node),
        )

    def _parse_method(self, node, source_bytes: bytes, file_str: str) -> ParsedEntity:
        name_node = node.child_by_field_name("name")
        name = node_text(name_node, source_bytes) if name_node else "anonymous"
        receiver_node = node.child_by_field_name("receiver")
        parent_type = None
        if receiver_node:
            for child in receiver_node.children:
                if child.type == "parameter_declaration":
                    type_node = child.child_by_field_name("type")
                    if type_node:
                        parent_type = node_text(type_node, source_bytes).strip("*")

        params_node = node.child_by_field_name("parameters")
        params = self._parse_parameters(params_node, source_bytes) if params_node else []
        result_node = node.child_by_field_name("result")
        return_type = node_text(result_node, source_bytes) if result_node else None

        return ParsedEntity(
            name=name,
            entity_type="method",
            file_path=file_str,
            line_start=node.start_point[0],
            line_end=node.end_point[0],
            language="go",
            parent=parent_type,
            parameters=params,
            return_type=return_type,
            complexity=estimate_complexity(node),
        )

    def _parse_import(self, node, source_bytes: bytes, file_str: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        for child in node.children:
            if child.type == "import_spec":
                path_node = child.child_by_field_name("path")
                import_source = node_text(path_node, source_bytes).strip('"') if path_node else ""
                alias_node = child.child_by_field_name("name")
                import_name = node_text(alias_node, source_bytes) if alias_node else import_source.split("/")[-1]

                entities.append(ParsedEntity(
                    name=f"from_{import_source}",
                    entity_type="import",
                    file_path=file_str,
                    line_start=child.start_point[0],
                    line_end=child.end_point[0],
                    language="go",
                    import_source=import_source,
                    import_names=[import_name],
                    is_from_import=False,
                ))
        return entities

    def _parse_parameters(self, params_node, source_bytes: bytes) -> list[str]:
        params: list[str] = []
        for child in params_node.children:
            if child.type == "parameter_declaration":
                names: list[str] = []
                type_node = child.child_by_field_name("type")
                type_text = node_text(type_node, source_bytes) if type_node else ""
                for sub in child.children:
                    if sub.type == "identifier":
                        names.append(node_text(sub, source_bytes))
                for name in names:
                    if type_text:
                        params.append(f"{name}: {type_text}")
                    else:
                        params.append(name)
            elif child.type == "variadic_parameter":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                if name_node and type_node:
                    params.append(f"...{node_text(name_node, source_bytes)}: {node_text(type_node, source_bytes)}")
        return params
