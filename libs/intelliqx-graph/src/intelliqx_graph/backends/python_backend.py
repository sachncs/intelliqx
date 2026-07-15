from __future__ import annotations

from textwrap import indent

from intelliqx_graph.backends.base import CodeBackend
from intelliqx_graph.models import (
    NodeType,
    SGIRNode,
    SoftwareGraph,
)


class PythonBackend(CodeBackend):
    @property
    def language(self) -> str:
        return "python"

    def generate(self, graph: SoftwareGraph) -> dict[str, str]:
        files: dict[str, str] = {}
        nodes_by_type = self.classify_nodes(graph)

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
            module_classes = [
                c for c in class_nodes if self.is_child_of(c, module, graph)
            ]
            module_functions = [
                f for f in function_nodes if self.is_child_of(f, module, graph)
            ]
            module_methods = [
                m for m in method_nodes if self.is_child_of(m, module, graph)
            ]
            module_datamodels = [
                d for d in datamodel_nodes if self.is_child_of(d, module, graph)
            ]
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
            if not any(
                self.is_child_of(n, m, graph) for m in module_nodes
            )
        ]
        if orphans:
            file_path = f"{graph.repository.name.replace(' ', '_').lower()}.py"
            if file_path not in files:
                files[file_path] = self.generate_single_file(
                    graph, orphans, [], [], []
                )

        return files

    def classify_nodes(self, graph: SoftwareGraph) -> dict[NodeType, list[SGIRNode]]:
        classified: dict[NodeType, list[SGIRNode]] = {}
        for layer_graph in graph.layers.values():
            for node in layer_graph.nodes:
                classified.setdefault(node.node_type, []).append(node)
        return classified

    def is_child_of(self, child: SGIRNode, parent: SGIRNode, graph: SoftwareGraph) -> bool:
        for layer_graph in graph.layers.values():
            for edge in layer_graph.edges:
                if edge.source == parent.id and edge.target == child.id:
                    return True
        if child.source_location and parent.source_location:
            return (
                child.source_location.file_path == parent.source_location.file_path
                and child.source_location.line_start >= parent.source_location.line_start
                and child.source_location.line_end <= parent.source_location.line_end
            )
        return False

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
        bases = self.get_inheritance(cls, graph)
        base_str = f"({', '.join(bases)})" if bases else ""
        parts = [f"class {self.safe_name(cls.name)}{base_str}:"]
        if cls.purpose:
            parts.append(indent(f'"""{cls.purpose}"""', "    "))
        class_methods = [
            m for m in all_methods if self.is_child_of(m, cls, graph)
        ]
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

    def get_inheritance(self, cls: SGIRNode, graph: SoftwareGraph) -> list[str]:
        bases: list[str] = []
        for layer_graph in graph.layers.values():
            for edge in layer_graph.edges:
                if edge.target == cls.id and edge.source in (
                    e.source for e in layer_graph.edges if e.target == cls.id
                ):
                    source_node = graph.find_node(edge.source)
                    if source_node and source_node.node_type == NodeType.CLASS:
                        bases.append(self.safe_name(source_node.name))
        return bases

    def collect_imports(self, graph: SoftwareGraph) -> list[str]:
        seen: set[str] = set()
        imports: list[str] = []
        for layer_graph in graph.layers.values():
            for edge in layer_graph.edges:
                if edge.edge_type.value == "import":
                    source_node = graph.find_node(edge.source)
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
