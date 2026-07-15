"""Python AST parser.

Uses the stdlib ``ast`` module to parse Python source files into
``ParsedEntity`` objects. Extracts functions, classes, methods,
imports, decorators, and basic complexity estimates.
"""

from __future__ import annotations

import ast
from pathlib import Path

from intelliqx_graph.parsers import BaseParser, ParsedEntity

COMPLEXITY_CONSTANT_MAX: int = 1
COMPLEXITY_LINEAR_MAX: int = 3
COMPLEXITY_LINEARITHMIC_MAX: int = 6
COMPLEXITY_QUADRATIC_MAX: int = 10


def estimate_complexity(node: ast.AST) -> str:
    """Rough cyclomatic complexity estimate from AST nodes."""
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            complexity += 1

    if complexity <= COMPLEXITY_CONSTANT_MAX:
        return "O(1)"
    elif complexity <= COMPLEXITY_LINEAR_MAX:
        return "O(n)"
    elif complexity <= COMPLEXITY_LINEARITHMIC_MAX:
        return "O(n log n)"
    elif complexity <= COMPLEXITY_QUADRATIC_MAX:
        return "O(n^2)"
    else:
        return "O(n^3)"


def extract_decorators(node: ast.AST) -> list[str]:
    """Extract decorator names from a function or class node."""
    decorators: list[str] = []
    for dec in getattr(node, "decorator_list", []):
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            decorators.append(f"{ast.dump(dec.value)}.{dec.attr}" if hasattr(dec, 'value') else dec.attr)
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name):
                decorators.append(dec.func.id)
            elif isinstance(dec.func, ast.Attribute):
                decorators.append(dec.func.attr)
        else:
            decorators.append(ast.dump(dec))
    return decorators


def get_name_from_annotation(node: ast.AST | None) -> str | None:
    """Best-effort extraction of a type annotation as a string."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


class PythonParser(BaseParser):
    """Python AST parser using stdlib ``ast`` module."""

    @property
    def language(self) -> str:
        return "python"

    def supported_extensions(self) -> list[str]:
        return [".py", ".pyi"]

    def parse_file(self, file_path: Path) -> list[ParsedEntity]:
        """Parse a Python file into entities."""
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return []

        entities: list[ParsedEntity] = []
        file_str = str(file_path)

        for node in ast.iter_child_nodes(tree):
            entities.extend(self.parse_node(node, file_str, parent=None))

        return entities

    def parse_node(
        self, node: ast.AST, file_str: str, parent: str | None
    ) -> list[ParsedEntity]:
        """Recursively parse an AST node."""
        entities: list[ParsedEntity] = []

        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            entities.append(self.parse_function(node, file_str, parent))

        elif isinstance(node, ast.ClassDef):
            class_entity = self.parse_class(node, file_str, parent)
            entities.append(class_entity)
            # Parse methods inside the class
            for child in ast.iter_child_nodes(node):
                child_entities = self.parse_node(child, file_str, parent=node.name)
                entities.extend(child_entities)

        elif isinstance(node, ast.Import | ast.ImportFrom):
            entities.append(self.parse_import(node, file_str))

        return entities

    def parse_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, file_str: str, parent: str | None
    ) -> ParsedEntity:
        """Parse a function or method definition."""
        params: list[str] = []
        for arg in node.args.args:
            ann = get_name_from_annotation(arg.annotation)
            if ann:
                params.append(f"{arg.arg}: {ann}")
            else:
                params.append(arg.arg)

        return ParsedEntity(
            name=node.name,
            entity_type="method" if parent else "function",
            file_path=file_str,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno) or node.lineno,
            language="python",
            parent=parent,
            parameters=params,
            return_type=get_name_from_annotation(node.returns),
            is_async=isinstance(node, ast.AsyncFunctionDef),
            decorators=extract_decorators(node),
            docstring=ast.get_docstring(node),
            complexity=estimate_complexity(node),
        )

    def parse_class(self, node: ast.ClassDef, file_str: str, parent: str | None) -> ParsedEntity:
        """Parse a class definition."""
        bases: list[str] = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                bases.append(ast.dump(base))

        return ParsedEntity(
            name=node.name,
            entity_type="class",
            file_path=file_str,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno) or node.lineno,
            language="python",
            parent=parent,
            bases=bases,
            decorators=extract_decorators(node),
            docstring=ast.get_docstring(node),
        )

    def parse_import(self, node: ast.Import | ast.ImportFrom, file_str: str) -> ParsedEntity:
        """Parse an import statement."""
        if isinstance(node, ast.ImportFrom):
            import_names = [alias.name for alias in node.names]
            return ParsedEntity(
                name=f"from_{node.module or ''}",
                entity_type="import",
                file_path=file_str,
                line_start=node.lineno,
                line_end=node.lineno,
                language="python",
                import_source=node.module or "",
                import_names=import_names,
                is_from_import=True,
            )
        else:
            import_names = [alias.name for alias in node.names]
            return ParsedEntity(
                name=f"import_{import_names[0] if import_names else 'unknown'}",
                entity_type="import",
                file_path=file_str,
                line_start=node.lineno,
                line_end=node.lineno,
                language="python",
                import_source="",
                import_names=import_names,
                is_from_import=False,
            )
