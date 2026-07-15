from __future__ import annotations

from textwrap import indent
from typing import TYPE_CHECKING, ClassVar

from intelliqx_graph.backends.base import CodeBackend
from intelliqx_graph.models import (
    NodeType,
    SGIRNode,
    SoftwareGraph,
)

if TYPE_CHECKING:
    from intelliqx_graph.models import SGIREdge


class _GenerateHelper:
    """Cached indexes over a :class:`SoftwareGraph` for code generation.

    Code generation repeatedly asks ``is_child_of`` and
    ``graph.find_node`` style queries. The naive implementations
    walk every node and every edge per call which, against a
    non-trivial source repo, makes code generation time cubic in
    the number of nodes (~5M ops for 1600-node graph) and was
    timing out the self-improvement run.

    This helper pre-builds:

    * ``nodes_by_type`` — group nodes by their ``NodeType`` so the
      per-module gather is O(1) per candidate.
    * ``node_by_id`` — O(1) ``id → SGIRNode`` lookup.
    * ``children_of_parent`` and ``parents_of_child`` — adjacency
      lists inverted from the edge layer, so ``is_child_of`` is
      O(1) average case.
    * ``import_edges`` — pre-filtered list of import-typed edges.

    The class is keyed per ``SoftwareGraph`` so two generation
    passes over the same graph share indexes.
    """

    __slots__ = (
        "children_of_parent",
        "import_edges",
        "node_by_id",
        "nodes_by_type",
        "parents_of_child",
    )

    _CACHE: ClassVar[dict[int, _GenerateHelper]] = {}

    @classmethod
    def build(cls, graph: SoftwareGraph) -> _GenerateHelper:
        cached = cls._CACHE.get(id(graph))
        if cached is not None:
            return cached
        helper = cls.__new__(cls)
        nodes_by_type: dict[NodeType, list[SGIRNode]] = {}
        node_by_id: dict[str, SGIRNode] = {}
        for layer_graph in graph.layers.values():
            for node in layer_graph.nodes:
                nodes_by_type.setdefault(node.node_type, []).append(node)
                node_by_id[node.id] = node
        children_of_parent: dict[str, list[SGIRNode]] = {}
        parents_of_child: dict[str, list[SGIRNode]] = {}
        import_edges: list[SGIREdge] = []
        for layer_graph in graph.layers.values():
            for edge in layer_graph.edges:
                target = node_by_id.get(edge.target)
                source = node_by_id.get(edge.source)
                if source is not None and target is not None:
                    children_of_parent.setdefault(edge.source, []).append(target)
                    parents_of_child.setdefault(edge.target, []).append(source)
                # ``edge.edge_type`` is an enum; the value comparison is
                # cheap and avoids importing the full enum at module scope.
                if edge.edge_type.value == "import":
                    import_edges.append(edge)
        helper.nodes_by_type = nodes_by_type
        helper.node_by_id = node_by_id
        helper.children_of_parent = children_of_parent
        helper.parents_of_child = parents_of_child
        helper.import_edges = import_edges
        cls._CACHE[id(graph)] = helper
        return helper

    def find_node(self, node_id: str) -> SGIRNode | None:
        return self.node_by_id.get(node_id)

    def children_of(
        self, parent: SGIRNode, candidates: list[SGIRNode]
    ) -> list[SGIRNode]:
        child_ids = {c.id for c in self.children_of_parent.get(parent.id, ())}
        return [c for c in candidates if c.id in child_ids]

    def is_child_of(self, child: SGIRNode, parent: SGIRNode) -> bool:
        return any(
            p.id == parent.id for p in self.parents_of_child.get(child.id, ())
        )

    def parents_of(self, child: SGIRNode) -> list[SGIRNode]:
        return self.parents_of_child.get(child.id, ())

    def is_under_modules(
        self, node: SGIRNode, modules: list[SGIRNode]
    ) -> bool:
        module_ids = {m.id for m in modules}
        for parent in self.parents_of(node):
            if parent.id in module_ids:
                return True
        # Fall back to source-location containment (matches the
        # original ``is_child_of`` semantics).
        if node.source_location and node.source_location.file_path:
            for module in modules:
                if module.source_location and module.source_location.file_path == node.source_location.file_path:
                    return True
        return False


class PythonBackend(CodeBackend):
    @property
    def language(self) -> str:
        return "python"

    def generate(self, graph: SoftwareGraph) -> dict[str, str]:
        files: dict[str, str] = {}
        # Pre-compute the helper indexes used by every child-emit pass
        # below. The previous implementation re-walked all layers and
        # all edges on every ``is_child_of`` call, which turned code
        # generation into a class x edges x layers double-loop.
        helper = _GenerateHelper.build(graph)
        nodes_by_type = helper.nodes_by_type

        module_nodes = nodes_by_type.get(NodeType.MODULE, [])
        package_nodes = nodes_by_type.get(NodeType.PACKAGE, [])
        class_nodes = nodes_by_type.get(NodeType.CLASS, [])
        function_nodes = nodes_by_type.get(NodeType.FUNCTION, [])
        method_nodes = nodes_by_type.get(NodeType.METHOD, [])
        datamodel_nodes = nodes_by_type.get(NodeType.DATAMODEL, [])

        if not module_nodes and not package_nodes:
            file_path = f"{graph.repository.name.replace(' ', '_').lower()}.py"
            files[file_path] = self.generate_single_file(
                graph, class_nodes, function_nodes, method_nodes, datamodel_nodes
            )
            return files

        for module in module_nodes:
            file_path = self.node_to_file_path(module)
            module_classes = helper.children_of(module, class_nodes)
            module_functions = helper.children_of(module, function_nodes)
            module_methods = helper.children_of(module, method_nodes)
            module_datamodels = helper.children_of(module, datamodel_nodes)
            files[file_path] = self.generate_module_file(
                graph, module, module_classes, module_functions, module_methods, module_datamodels
            )

        for package in package_nodes:
            dir_path = self.node_to_dir_path(package)
            init_path = f"{dir_path}/__init__.py"
            if init_path not in files:
                files[init_path] = self.generate_package_init(package)

        orphans = [
            n for n in class_nodes + function_nodes + datamodel_nodes
            if not helper.is_under_modules(n, module_nodes)
        ]
        if orphans:
            file_path = f"{graph.repository.name.replace(' ', '_').lower()}.py"
            if file_path not in files:
                files[file_path] = self.generate_single_file(
                    graph, orphans, [], [], []
                )

        return files

    def classify_nodes(self, graph: SoftwareGraph) -> dict[NodeType, list[SGIRNode]]:
        return _GenerateHelper.build(graph).nodes_by_type

    def is_child_of(self, child: SGIRNode, parent: SGIRNode, graph: SoftwareGraph) -> bool:
        return _GenerateHelper.build(graph).is_child_of(child, parent)

    def node_to_file_path(self, node: SGIRNode) -> str:
        if node.source_location:
            return node.source_location.file_path
        name = node.name.replace(".", "/").replace("-", "_").lower()
        return f"{name}.py"

    def node_to_dir_path(self, node: SGIRNode) -> str:
        if node.source_location:
            return node.source_location.file_path.rstrip("/")
        return node.name.replace(".", "/").replace("-", "_").lower()

    def generate_single_file(
        self,
        graph: SoftwareGraph,
        classes: list[SGIRNode],
        functions: list[SGIRNode],
        methods: list[SGIRNode],
        datamodels: list[SGIRNode],
    ) -> str:
        sections: list[str] = []
        imports = self.collect_imports(graph)
        if imports:
            sections.append("\n".join(imports))
        for dm in datamodels:
            sections.append(self.generate_datamodel(dm))
        for cls in classes:
            sections.append(self.generate_class(cls, methods, graph))
        for func in functions:
            if func.node_type != NodeType.METHOD:
                sections.append(self.generate_function(func))
        return self.format_code("\n\n".join(sections))

    def generate_module_file(
        self,
        graph: SoftwareGraph,
        module: SGIRNode,
        classes: list[SGIRNode],
        functions: list[SGIRNode],
        methods: list[SGIRNode],
        datamodels: list[SGIRNode],
    ) -> str:
        sections: list[str] = []
        if module.purpose:
            sections.append(f'"""{module.purpose}"""')
        imports = self.collect_imports_for_node(module, graph)
        if imports:
            sections.append("\n".join(imports))
        for dm in datamodels:
            sections.append(self.generate_datamodel(dm))
        for cls in classes:
            sections.append(self.generate_class(cls, methods, graph))
        for func in functions:
            if func.node_type != NodeType.METHOD:
                sections.append(self.generate_function(func))
        if not sections:
            sections.append("pass")
        return self.format_code("\n\n".join(sections))

    def generate_package_init(self, package: SGIRNode) -> str:
        parts: list[str] = []
        if package.purpose:
            parts.append(f'"""{package.purpose}"""')
        return self.format_code("\n".join(parts) if parts else "")

    def generate_class(
        self, cls: SGIRNode, all_methods: list[SGIRNode], graph: SoftwareGraph
    ) -> str:
        helper = _GenerateHelper.build(graph)
        bases = self.get_inheritance(cls, helper)
        base_str = f"({', '.join(bases)})" if bases else ""
        parts = [f"class {self.safe_name(cls.name)}{base_str}:"]
        if cls.purpose:
            parts.append(indent(f'"""{cls.purpose}"""', "    "))
        class_methods = helper.children_of(cls, all_methods)
        if not class_methods:
            parts.append(indent("pass", "    "))
        else:
            for method in class_methods:
                parts.append("")
                parts.append(self.generate_method(method))
        return "\n".join(parts)

    def generate_method(self, method: SGIRNode) -> str:
        params = self.inputs_to_params(method)
        ret = self.outputs_to_return_type(method)
        sig = f"def {self.safe_name(method.name)}({params}){ret}:"
        body = self.generate_body(method)
        return indent(f"{sig}\n{body}", "    ")

    def generate_function(self, func: SGIRNode) -> str:
        params = self.inputs_to_params(func)
        ret = self.outputs_to_return_type(func)
        sig = f"def {self.safe_name(func.name)}({params}){ret}:"
        body = self.generate_body(func)
        return f"{sig}\n{body}"

    def generate_datamodel(self, dm: SGIRNode) -> str:
        fields = self.inputs_to_fields(dm)
        parts = [f"class {self.safe_name(dm.name)}:"]
        if dm.purpose:
            parts.append(indent(f'"""{dm.purpose}"""', "    "))
        if fields:
            parts.append(indent("pass", "    "))
        else:
            parts.append(indent("pass", "    "))
        return "\n".join(parts)

    def generate_body(self, node: SGIRNode) -> str:
        lines = ["pass"]
        if node.purpose:
            lines = [f'"""{node.purpose}"""']
        return indent("\n".join(lines), "    ")

    def inputs_to_params(self, node: SGIRNode) -> str:
        params = ["self"] if node.node_type == NodeType.METHOD else []
        for inp in node.inputs:
            parts = inp.split(":")
            name = self.safe_name(parts[0].strip())
            if len(parts) > 1:
                params.append(f"{name}: {parts[1].strip()}")
            else:
                params.append(name)
        return ", ".join(params)

    def inputs_to_fields(self, node: SGIRNode) -> list[str]:
        fields = []
        for inp in node.inputs:
            parts = inp.split(":")
            name = self.safe_name(parts[0].strip())
            if len(parts) > 1:
                fields.append(f"{name}: {parts[1].strip()}")
            else:
                fields.append(name)
        return fields

    def outputs_to_return_type(self, node: SGIRNode) -> str:
        if not node.outputs:
            return ""
        if len(node.outputs) == 1:
            return f" -> {node.outputs[0].strip()}"
        types = ", ".join(o.strip() for o in node.outputs)
        return f" -> tuple[{types}]"

    def get_inheritance(
        self, cls: SGIRNode, helper: _GenerateHelper
    ) -> list[str]:
        bases: list[str] = []
        for source in helper.parents_of(cls):
            if source.node_type == NodeType.CLASS:
                bases.append(self.safe_name(source.name))
        return bases

    def collect_imports(self, graph: SoftwareGraph) -> list[str]:
        helper = _GenerateHelper.build(graph)
        seen: set[str] = set()
        imports: list[str] = []
        for edge in helper.import_edges:
            source_node = helper.find_node(edge.source)
            if source_node and source_node.name not in seen:
                seen.add(source_node.name)
                imports.append(f"import {source_node.name}")
        return imports

    def collect_imports_for_node(self, node: SGIRNode, graph: SoftwareGraph) -> list[str]:
        deps = node.external_dependencies
        if not deps:
            return []
        return [f"import {dep}" for dep in deps]

    def safe_name(self, name: str) -> str:
        return name.replace("-", "_").replace(".", "_").replace(" ", "_")
