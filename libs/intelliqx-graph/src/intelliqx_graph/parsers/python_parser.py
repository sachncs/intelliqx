"""Python AST parser.

Walks the stdlib ``ast`` tree with an ``ast.NodeVisitor`` and tracks
nested scopes so functions, methods, classes and imports are emitted
in source order with complete signatures, decorator names, call and
reference labels and stable source locations.

Syntax errors and unreadable files are not swallowed here: they
propagate to :meth:`intelliqx_graph.parsers.BaseParser.parse_files`
which records them in ``ParseResult.errors``.
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
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            complexity += 1

    if complexity <= COMPLEXITY_CONSTANT_MAX:
        return "O(1)"
    if complexity <= COMPLEXITY_LINEAR_MAX:
        return "O(n)"
    if complexity <= COMPLEXITY_LINEARITHMIC_MAX:
        return "O(n log n)"
    if complexity <= COMPLEXITY_QUADRATIC_MAX:
        return "O(n^2)"
    return "O(n^3)"


def unparse(node: ast.AST | None) -> str | None:
    """Best-effort ``ast.unparse`` that never raises."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def decorator_label(dec: ast.AST) -> str | None:
    """Render a decorator as a dotted or called name string.

    ``@foo`` -> ``"foo"``
    ``@mod.foo`` -> ``"mod.foo"``
    ``@mod.foo(...)`` -> ``"mod.foo(...)"``
    ``@mod.foo[Bar](...)`` -> falls back to ``ast.unparse``.
    Returns ``None`` only when ``ast.unparse`` cannot render it.
    """
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        head = decorator_label(dec.value)
        if head is None:
            return dec.attr
        return f"{head}.{dec.attr}"
    return unparse(dec)


def annotation_text(node: ast.AST | None) -> str | None:
    """Best-effort type annotation as a string."""
    return unparse(node)


class _YieldSearcher(ast.NodeVisitor):
    """Detect ``yield`` / ``yield from`` while skipping nested scopes.

    Yields inside a nested function, comprehension or lambda belong to
    that nested scope, not to the enclosing function or class body.
    """

    def __init__(self) -> None:
        self.found = False

    def visit_Yield(self, node: ast.Yield) -> None:
        self.found = True

    def visit_YieldFrom(self, node: ast.YieldFrom) -> None:
        self.found = True

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        pass

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        pass

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        pass

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        pass


def contains_direct_yield(body: list[ast.stmt]) -> bool:
    """Return True if ``body`` yields at its own scope level.

    ``yield`` inside a nested function, nested class or comprehension
    does not make the enclosing function a generator — those yields
    belong to the inner scope.
    """
    searcher = _YieldSearcher()
    for stmt in body:
        searcher.visit(stmt)
        if searcher.found:
            return True
    return False


class _ScopeFrame:
    """One frame on the scope stack: function or class we are inside."""

    __slots__ = ("calls", "kind", "name", "references", "target")

    def __init__(self, kind: str, name: str, target: ParsedEntity) -> None:
        self.kind = kind
        self.name = name
        self.target = target
        self.calls: list[str] = []
        self.references: list[str] = []


class _PythonFileVisitor(ast.NodeVisitor):
    """Visits a parsed module and emits ``ParsedEntity`` records in source order."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.file_str = str(file_path)
        self.entities: list[ParsedEntity] = []
        self.scope_stack: list[_ScopeFrame] = []

    def line_end(self, node: ast.AST) -> int:
        end = getattr(node, "end_lineno", None)
        if isinstance(end, int):
            return end
        return getattr(node, "lineno", 1)

    def parent_name(self) -> str | None:
        if not self.scope_stack:
            return None
        return self.scope_stack[-1].name

    def parent_kind(self) -> str | None:
        if not self.scope_stack:
            return None
        return self.scope_stack[-1].kind

    def current_callable(self) -> _ScopeFrame | None:
        for frame in reversed(self.scope_stack):
            if frame.kind == "function":
                return frame
        return None

    def enclosing_frame(self) -> _ScopeFrame | None:
        for frame in reversed(self.scope_stack):
            if frame.kind in {"function", "class"}:
                return frame
        return None

    def _defaults_for_positional(
        self, posonly: list[ast.arg], regular: list[ast.arg], defaults: list[ast.expr]
    ) -> dict[str, ast.expr]:
        """Map defaults to the rightmost N positional args across posonly+regular."""
        combined: list[ast.arg] = list(posonly) + list(regular)
        offset = len(combined) - len(defaults)
        result: dict[str, ast.expr] = {}
        for i, default in enumerate(defaults):
            if 0 <= offset + i < len(combined):
                result[combined[offset + i].arg] = default
        return result

    def render_parameters_with_defaults(self, args: ast.arguments) -> list[str]:
        pos_defaults = self._defaults_for_positional(args.posonlyargs, args.args, args.defaults)
        kw_defaults = dict(zip((a.arg for a in args.kwonlyargs), args.kw_defaults))
        parts: list[str] = []
        for arg in args.posonlyargs:
            parts.append(self._render_arg(arg, default=pos_defaults.get(arg.arg)))
        if args.posonlyargs:
            parts.append("/")
        for arg in args.args:
            parts.append(self._render_arg(arg, default=pos_defaults.get(arg.arg)))
        if args.vararg:
            parts.append(self._render_arg(args.vararg, star="*"))
        elif args.kwonlyargs:
            parts.append("*")
        for arg in args.kwonlyargs:
            parts.append(self._render_arg(arg, default=kw_defaults.get(arg.arg)))
        if args.kwarg:
            parts.append(self._render_arg(args.kwarg, star="**"))
        return parts

    def _render_arg(self, arg: ast.arg, *, default: ast.AST | None = None, star: str = "") -> str:
        name = arg.arg
        ann = annotation_text(arg.annotation)
        rendered = f"{star}{name}"
        if ann is not None:
            rendered = f"{rendered}: {ann}"
        if default is not None:
            default_text = unparse(default)
            if default_text is not None:
                rendered = f"{rendered} = {default_text}"
        return rendered

    def extract_bases(self, node: ast.ClassDef) -> list[str]:
        names: list[str] = []
        for base in node.bases:
            text = unparse(base)
            if text is not None:
                names.append(text)
        for kw in node.keywords:
            text = unparse(kw.value)
            if text is not None:
                arg = f"{kw.arg}=" if kw.arg else ""
                names.append(f"{arg}{text}")
        return names

    def extract_decorators(self, node: ast.AST) -> list[str]:
        labels: list[str] = []
        for dec in getattr(node, "decorator_list", []):
            label = decorator_label(dec)
            if label is not None:
                labels.append(label)
        return labels

    def _populate_entity(self, frame: _ScopeFrame, entity: ParsedEntity) -> None:
        entity.calls = list(frame.calls)
        entity.references = list(frame.references)

    def visit_Module(self, node: ast.Module) -> None:
        for child in node.body:
            self.visit(child)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        parent = self.parent_name()
        bases = self.extract_bases(node)
        decorators = self.extract_decorators(node)
        docstring = ast.get_docstring(node)

        entity = self.make_entity(
            node,
            name=node.name,
            entity_type="class",
            parent=parent,
            parameters=[],
            return_type=None,
            is_async=False,
            is_generator=False,
            bases=bases,
            decorators=decorators,
            docstring=docstring,
            calls=[],
            references=[],
        )
        self.entities.append(entity)

        frame = _ScopeFrame(kind="class", name=node.name, target=entity)
        self.scope_stack.append(frame)
        try:
            for child in node.body:
                self.visit(child)
        finally:
            self.scope_stack.pop()
            self._populate_entity(frame, entity)

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        parent = self.parent_name()
        parent_kind = self.parent_kind()
        is_method = parent_kind == "class"

        is_async = isinstance(node, ast.AsyncFunctionDef)
        is_generator = contains_direct_yield(node.body)

        parameters = self.render_parameters_with_defaults(node.args)
        return_type = annotation_text(node.returns)
        decorators = self.extract_decorators(node)
        docstring = ast.get_docstring(node)

        entity = self.make_entity(
            node,
            name=node.name,
            entity_type="method" if is_method else "function",
            parent=parent,
            parameters=parameters,
            return_type=return_type,
            is_async=is_async,
            is_generator=is_generator,
            bases=[],
            decorators=decorators,
            docstring=docstring,
            calls=[],
            references=[],
        )
        self.entities.append(entity)

        frame = _ScopeFrame(kind="function", name=node.name, target=entity)
        self.scope_stack.append(frame)
        try:
            for child in node.body:
                self.visit(child)
        finally:
            self.scope_stack.pop()
            self._populate_entity(frame, entity)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func(node)

    def visit_Import(self, node: ast.Import) -> None:
        line_start = node.lineno
        line_end = self.line_end(node)
        for alias in node.names:
            imported = alias.name
            asname = alias.asname
            head = imported.split(".")[0]
            self.entities.append(
                ParsedEntity(
                    name=asname or imported,
                    entity_type="import",
                    file_path=self.file_str,
                    line_start=line_start,
                    line_end=line_end,
                    language="python",
                    import_source=imported,
                    import_names=[imported],
                    is_from_import=False,
                    import_aliases=[asname] if asname else [],
                    import_level=0,
                )
            )
            self._add_reference(head)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        line_start = node.lineno
        line_end = self.line_end(node)
        module = node.module or ""
        for alias in node.names:
            imported_name = alias.name
            asname = alias.asname
            self.entities.append(
                ParsedEntity(
                    name=asname or imported_name,
                    entity_type="import",
                    file_path=self.file_str,
                    line_start=line_start,
                    line_end=line_end,
                    language="python",
                    import_source=module,
                    import_names=[imported_name],
                    is_from_import=True,
                    import_aliases=[asname] if asname else [],
                    import_level=node.level,
                )
            )
        if module:
            self._add_reference(module.split(".")[0])

    def visit_Call(self, node: ast.Call) -> None:
        self._record_call(node.func)
        for arg in node.args:
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw.value)

    def _record_call(self, func_expr: ast.AST) -> None:
        if isinstance(func_expr, ast.Name):
            self._record_call_target(func_expr.id)
            self._add_reference(func_expr.id)
            return
        if isinstance(func_expr, ast.Attribute):
            self._record_call_target(func_expr.attr)
            self._add_reference(func_expr.attr)
            self.visit(func_expr.value)
            return
        text = unparse(func_expr)
        if text:
            self._record_call_target(text)

    def _record_call_target(self, name: str) -> None:
        if not name:
            return
        frame = self.current_callable()
        if frame is not None and name not in frame.calls:
            frame.calls.append(name)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.visit(node.value)
        self._add_reference(node.attr)

    def visit_Name(self, node: ast.Name) -> None:
        self._add_reference(node.id)

    def _add_reference(self, name: str) -> None:
        if not name:
            return
        frame = self.enclosing_frame()
        if frame is None:
            return
        if name in frame.references:
            return
        frame.references.append(name)

    def make_entity(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        *,
        name: str,
        entity_type: str,
        parent: str | None,
        parameters: list[str],
        return_type: str | None,
        is_async: bool,
        is_generator: bool,
        bases: list[str],
        decorators: list[str],
        docstring: str | None,
        calls: list[str],
        references: list[str],
    ) -> ParsedEntity:
        return ParsedEntity(
            name=name,
            entity_type=entity_type,
            file_path=self.file_str,
            line_start=node.lineno,
            line_end=self.line_end(node),
            language="python",
            parent=parent,
            parameters=parameters,
            return_type=return_type,
            is_async=is_async,
            is_generator=is_generator,
            bases=bases,
            decorators=decorators,
            docstring=docstring,
            calls=calls,
            references=references,
        )


class PythonParser(BaseParser):
    """Python AST parser backed by the stdlib ``ast`` module."""

    @property
    def language(self) -> str:
        return "python"

    def supported_extensions(self) -> list[str]:
        return [".py", ".pyi"]

    def parse_file(self, file_path: Path) -> list[ParsedEntity]:
        """Parse a single ``.py`` / ``.pyi`` file into entities.

        ``SyntaxError`` and file-read errors propagate so the caller
        (``BaseParser.parse_files`` or :func:`parse_repository`) can
        record them in ``ParseResult.errors`` instead of swallowing
        them silently.
        """
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
        visitor = _PythonFileVisitor(file_path=file_path)
        visitor.visit(tree)
        return visitor.entities
