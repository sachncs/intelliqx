"""TypeScript/JavaScript tree-sitter parser.

Uses ``tree_sitter_languages`` to parse TypeScript and JavaScript
source files into ``ParsedEntity`` objects. Extracts functions,
classes, methods, imports, and basic complexity estimates.
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
        if type_name in ("if_statement", "while_statement", "for_statement", "switch_case", "catch_clause"):
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


class TypeScriptParser(BaseParser):
    """TypeScript/JavaScript tree-sitter parser."""

    @property
    def language(self) -> str:
        return "typescript"

    def supported_extensions(self) -> list[str]:
        return [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]

    def parse_file(self, file_path: Path) -> list[ParsedEntity]:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        source_bytes = bytes(source, "utf-8")

        try:
            parser = get_parser("typescript")
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

            if ctype in ("function_declaration", "generator_function_declaration"):
                entities.append(self._parse_function(child, source_bytes, file_str, parent))

            elif ctype == "method_definition":
                entities.append(self._parse_method(child, source_bytes, file_str, parent))

            elif ctype == "class_declaration":
                class_entity = self._parse_class(child, source_bytes, file_str, parent)
                entities.append(class_entity)
                self._walk(child, source_bytes, file_str, entities, parent=class_entity.name)

            elif ctype == "interface_declaration":
                class_entity = self._parse_interface(child, source_bytes, file_str, parent)
                entities.append(class_entity)
                self._walk(child, source_bytes, file_str, entities, parent=class_entity.name)

            elif ctype in ("import_statement",):
                entities.append(self._parse_import(child, source_bytes, file_str))

            elif ctype == "lexical_declaration":
                for grandchild in child.children:
                    if grandchild.type == "variable_declarator":
                        init = grandchild.child_by_field_name("value")
                        if init and init.type in ("arrow_function", "function"):
                            name_node = grandchild.child_by_field_name("name")
                            name = node_text(name_node, source_bytes) if name_node else "anonymous"
                            entities.append(ParsedEntity(
                                name=name,
                                entity_type="function",
                                file_path=file_str,
                                line_start=child.start_point[0],
                                line_end=child.end_point[0],
                                language="typescript",
                                parent=parent,
                                is_async=any(c.type == "async" for c in child.children),
                                complexity=estimate_complexity(init),
                            ))

            elif ctype == "function":
                name_node = child.child_by_field_name("name")
                name = node_text(name_node, source_bytes) if name_node else "anonymous"
                params_node = child.child_by_field_name("parameters")
                params = self._parse_parameters(params_node, source_bytes) if params_node else []
                entities.append(ParsedEntity(
                    name=name,
                    entity_type="function",
                    file_path=file_str,
                    line_start=child.start_point[0],
                    line_end=child.end_point[0],
                    language="typescript",
                    parent=parent,
                    parameters=params,
                    is_async=any(c.type == "async" for c in child.children),
                    complexity=estimate_complexity(child),
                ))

    def _parse_function(self, node, source_bytes: bytes, file_str: str, parent: str | None) -> ParsedEntity:
        name_node = node.child_by_field_name("name")
        name = node_text(name_node, source_bytes) if name_node else "anonymous"
        params_node = node.child_by_field_name("parameters")
        params = self._parse_parameters(params_node, source_bytes) if params_node else []

        return ParsedEntity(
            name=name,
            entity_type="method" if parent else "function",
            file_path=file_str,
            line_start=node.start_point[0],
            line_end=node.end_point[0],
            language="typescript",
            parent=parent,
            parameters=params,
            is_async=any(c.type == "async" for c in node.children),
            complexity=estimate_complexity(node),
        )

    def _parse_method(self, node, source_bytes: bytes, file_str: str, parent: str | None) -> ParsedEntity:
        name_node = node.child_by_field_name("name")
        name = node_text(name_node, source_bytes) if name_node else "anonymous"
        params_node = node.child_by_field_name("parameters")
        params = self._parse_parameters(params_node, source_bytes) if params_node else []
        is_static = any(c.type == "static" for c in node.children)

        return ParsedEntity(
            name=name,
            entity_type="method",
            file_path=file_str,
            line_start=node.start_point[0],
            line_end=node.end_point[0],
            language="typescript",
            parent=parent,
            parameters=params,
            is_static=is_static,
            is_async=any(c.type == "async" for c in node.children),
            complexity=estimate_complexity(node),
        )

    def _parse_class(self, node, source_bytes: bytes, file_str: str, parent: str | None) -> ParsedEntity:
        name_node = node.child_by_field_name("name")
        name = node_text(name_node, source_bytes) if name_node else "anonymous"

        bases: list[str] = []
        superclass = node.child_by_field_name("superclass")
        if superclass:
            bases.append(node_text(superclass, source_bytes))

        return ParsedEntity(
            name=name,
            entity_type="class",
            file_path=file_str,
            line_start=node.start_point[0],
            line_end=node.end_point[0],
            language="typescript",
            parent=parent,
            bases=bases,
        )

    def _parse_interface(self, node, source_bytes: bytes, file_str: str, parent: str | None) -> ParsedEntity:
        name_node = node.child_by_field_name("name")
        name = node_text(name_node, source_bytes) if name_node else "anonymous"
        return ParsedEntity(
            name=name,
            entity_type="class",
            file_path=file_str,
            line_start=node.start_point[0],
            line_end=node.end_point[0],
            language="typescript",
            parent=parent,
        )

    def _parse_import(self, node, source_bytes: bytes, file_str: str) -> ParsedEntity:
        source_text = node_text(node, source_bytes)
        import_source = ""
        import_names: list[str] = []
        is_from_import = False

        if "from" in source_text:
            is_from_import = True
            for child in node.children:
                if child.type == "string":
                    import_source = node_text(child, source_bytes).strip("'\"")
                elif child.type == "import_clause":
                    for sub in child.children:
                        if sub.type == "identifier":
                            import_names.append(node_text(sub, source_bytes))
                        elif sub.type == "named_imports":
                            for specifier in sub.children:
                                if specifier.type == "import_specifier":
                                    name = specifier.child_by_field_name("name") or specifier.child_by_field_name("alias")
                                    if name:
                                        import_names.append(node_text(name, source_bytes))
        else:
            for child in node.children:
                if child.type == "import_clause":
                    for sub in child.children:
                        if sub.type == "identifier":
                            import_names.append(node_text(sub, source_bytes))

        return ParsedEntity(
            name=f"from_{import_source}" if import_source else f"import_{import_names[0] if import_names else 'unknown'}",
            entity_type="import",
            file_path=file_str,
            line_start=node.start_point[0],
            line_end=node.end_point[0],
            language="typescript",
            import_source=import_source,
            import_names=import_names,
            is_from_import=is_from_import,
        )

    def _parse_parameters(self, params_node, source_bytes: bytes) -> list[str]:
        params: list[str] = []
        for child in params_node.children:
            if child.type == "required_parameter" or child.type == "optional_parameter":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                if name_node:
                    name_text = node_text(name_node, source_bytes)
                    if type_node:
                        params.append(f"{name_text}: {node_text(type_node, source_bytes)}")
                    else:
                        params.append(name_text)
            elif child.type == "rest_parameter":
                name_node = child.child_by_field_name("name")
                if name_node:
                    params.append(f"...{node_text(name_node, source_bytes)}")
        return params
