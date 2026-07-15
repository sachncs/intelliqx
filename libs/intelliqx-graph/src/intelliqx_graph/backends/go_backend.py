from __future__ import annotations

from intelliqx_graph.backends.base import CodeBackend
from intelliqx_graph.models import (
    NodeType,
    SGIRNode,
    SoftwareGraph,
)


class GoBackend(CodeBackend):
    @property
    def language(self) -> str:
        return "go"

    def generate(self, graph: SoftwareGraph) -> dict[str, str]:
        files: dict[str, str] = {}
        nodes_by_type = self.classify_nodes(graph)

        package_nodes = nodes_by_type.get(NodeType.PACKAGE, [])
        module_nodes = nodes_by_type.get(NodeType.MODULE, [])
        class_nodes = nodes_by_type.get(NodeType.CLASS, [])
        function_nodes = nodes_by_type.get(NodeType.FUNCTION, [])
        method_nodes = nodes_by_type.get(NodeType.METHOD, [])
        datamodel_nodes = nodes_by_type.get(NodeType.DATAMODEL, [])

        if not package_nodes and not module_nodes:
            pkg_name = self.to_go_package_name(graph.repository.name)
            file_path = f"{pkg_name}/{pkg_name}.go"
            files[file_path] = self.generate_single_file(
                graph, pkg_name, class_nodes, function_nodes, method_nodes, datamodel_nodes
            )
            return files

        for pkg in package_nodes:
            pkg_name = self.to_go_package_name(pkg.name)
            file_path = f"{pkg_name}/{pkg_name}.go"
            pkg_classes = [c for c in class_nodes if self.is_child_of(c, pkg, graph)]
            pkg_functions = [f for f in function_nodes if self.is_child_of(f, pkg, graph)]
            pkg_methods = [m for m in method_nodes if self.is_child_of(m, pkg, graph)]
            pkg_datamodels = [d for d in datamodel_nodes if self.is_child_of(d, pkg, graph)]
            files[file_path] = self.generate_package_file(
                graph, pkg_name, pkg_classes, pkg_functions, pkg_methods, pkg_datamodels
            )

        orphans = [
            n for n in class_nodes + function_nodes + datamodel_nodes
            if not any(self.is_child_of(n, p, graph) for p in package_nodes)
        ]
        if orphans:
            pkg_name = self.to_go_package_name(graph.repository.name)
            file_path = f"{pkg_name}/{pkg_name}.go"
            if file_path not in files:
                files[file_path] = self.generate_single_file(
                    graph, pkg_name, orphans, [], [], []
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

    def to_go_package_name(self, name: str) -> str:
        return name.replace("-", "_").replace(".", "_").replace(" ", "_").lower()

    def to_go_type(self, name: str) -> str:
        parts = name.replace("-", " ").replace("_", " ").split()
        return "".join(p.capitalize() for p in parts)

    def generate_single_file(
        self,
        graph: SoftwareGraph,
        pkg_name: str,
        classes: list[SGIRNode],
        functions: list[SGIRNode],
        methods: list[SGIRNode],
        datamodels: list[SGIRNode],
    ) -> str:
        sections: list[str] = [f"package {pkg_name}"]
        imports = self.collect_imports(graph)
        if imports:
            sections.append(self.format_imports(imports))
        for dm in datamodels:
            sections.append(self.generate_struct(dm))
        for cls in classes:
            sections.append(self.generate_struct(cls))
        for method in methods:
            sections.append(self.generate_method(method, classes, graph))
        for func in functions:
            if func.node_type != NodeType.METHOD:
                sections.append(self.generate_function(func))
        return self.format_code("\n\n".join(sections))

    def generate_package_file(
        self,
        graph: SoftwareGraph,
        pkg_name: str,
        classes: list[SGIRNode],
        functions: list[SGIRNode],
        methods: list[SGIRNode],
        datamodels: list[SGIRNode],
    ) -> str:
        sections: list[str] = [f"package {pkg_name}"]
        imports = self.collect_imports(graph)
        if imports:
            sections.append(self.format_imports(imports))
        for dm in datamodels:
            sections.append(self.generate_struct(dm))
        for cls in classes:
            sections.append(self.generate_struct(cls))
        for method in methods:
            sections.append(self.generate_method(method, classes, graph))
        for func in functions:
            if func.node_type != NodeType.METHOD:
                sections.append(self.generate_function(func))
        return self.format_code("\n\n".join(sections))

    def generate_struct(self, node: SGIRNode) -> str:
        type_name = self.to_go_type(node.name)
        parts = [f"type {type_name} struct {{"]
        for inp in node.inputs:
            field = self.to_go_field(inp)
            if field:
                parts.append(f"\t{field}")
        parts.append("}")
        if node.purpose:
            parts.insert(1, f"\t// {node.purpose}")
        return "\n".join(parts)

    def generate_function(self, func: SGIRNode) -> str:
        func_name = self.to_go_type(func.name)
        params = self.to_go_params(func)
        returns = self.to_go_returns(func)
        sig = f"func {func_name}({params}){returns} {{"
        body = self.generate_body_go(func)
        return f"{sig}\n{body}\n}}"

    def generate_method(self, method: SGIRNode, classes: list[SGIRNode], graph: SoftwareGraph) -> str:
        method_name = self.to_go_type(method.name)
        receiver = self.find_receiver_type(method, classes, graph)
        params = self.to_go_params(method, skip_first=True)
        returns = self.to_go_returns(method)
        sig = f"func ({receiver}) {method_name}({params}){returns} {{"
        body = self.generate_body_go(method)
        return f"{sig}\n{body}\n}}"

    def find_receiver_type(self, method: SGIRNode, classes: list[SGIRNode], graph: SoftwareGraph) -> str:
        for layer_graph in graph.layers.values():
            for edge in layer_graph.edges:
                if edge.target == method.id:
                    source_node = graph.find_node(edge.source)
                    if source_node and source_node.node_type == NodeType.CLASS:
                        type_name = self.to_go_type(source_node.name)
                        return f"*{type_name}"
        return "s *" + self.to_go_type(method.name)

    def to_go_params(self, node: SGIRNode, skip_first: bool = False) -> str:
        inputs = node.inputs
        if skip_first and inputs:
            inputs = inputs[1:]
        params = []
        for inp in inputs:
            parts = inp.split(":")
            name = parts[0].strip().replace("-", "_")
            if len(parts) > 1:
                go_type = self.map_go_type(parts[1].strip())
                params.append(f"{name} {go_type}")
            else:
                params.append(f"{name} interface{{}}")
        return ", ".join(params)

    def to_go_returns(self, node: SGIRNode) -> str:
        if not node.outputs:
            return ""
        if len(node.outputs) == 1:
            return f" {self.map_go_type(node.outputs[0].strip())}"
        types = " ".join(self.map_go_type(o.strip()) for o in node.outputs)
        return f" ({types})"

    def to_go_field(self, inp: str) -> str:
        parts = inp.split(":")
        name = parts[0].strip().replace("-", "_")
        if len(parts) > 1:
            go_type = self.map_go_type(parts[1].strip())
            return f"{self.to_go_type(name)} {go_type}"
        return ""

    def map_go_type(self, type_hint: str) -> str:
        mapping = {
            "str": "string",
            "int": "int",
            "int64": "int64",
            "float": "float64",
            "float64": "float64",
            "bool": "bool",
            "bytes": "[]byte",
            "list": "[]interface{}",
            "dict": "map[string]interface{}",
            "any": "interface{}",
            "None": "",
            "void": "",
        }
        return mapping.get(type_hint, self.to_go_type(type_hint))

    def format_imports(self, imports: list[str]) -> str:
        if len(imports) == 1:
            return f'import "{imports[0]}"'
        lines = ["import (", *(f'\t"{imp}"' for imp in imports), ")"]
        return "\n".join(lines)

    def collect_imports(self, graph: SoftwareGraph) -> list[str]:
        seen: set[str] = set()
        imports: list[str] = []
        for layer_graph in graph.layers.values():
            for edge in layer_graph.edges:
                if edge.edge_type.value == "import":
                    source_node = graph.find_node(edge.source)
                    if source_node and source_node.name not in seen:
                        seen.add(source_node.name)
                        imports.append(source_node.name)
        return imports

    def generate_body_go(self, node: SGIRNode) -> str:
        return "\tpass"
