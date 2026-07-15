from __future__ import annotations

from textwrap import indent

from intelliqx_graph.backends.base import CodeBackend
from intelliqx_graph.models import (
    NodeType,
    SGIRNode,
    SoftwareGraph,
)


class TypeScriptBackend(CodeBackend):
    @property
    def language(self) -> str:
        return "typescript"

    def generate(self, graph: SoftwareGraph) -> dict[str, str]:
        files: dict[str, str] = {}
        nodes_by_type = self._classify_nodes(graph)

        module_nodes = nodes_by_type.get(NodeType.MODULE, [])
        package_nodes = nodes_by_type.get(NodeType.PACKAGE, [])
        class_nodes = nodes_by_type.get(NodeType.CLASS, [])
        function_nodes = nodes_by_type.get(NodeType.FUNCTION, [])
        method_nodes = nodes_by_type.get(NodeType.METHOD, [])
        datamodel_nodes = nodes_by_type.get(NodeType.DATAMODEL, [])

        if not module_nodes and not package_nodes:
            file_path = f"src/{self._to_kebab_case(graph.repository.name)}.ts"
            files[file_path] = self._generate_single_file(
                graph, class_nodes, function_nodes, method_nodes, datamodel_nodes
            )
            return files

        for module in module_nodes:
            file_path = self._node_to_file_path(module)
            mod_classes = [c for c in class_nodes if self._is_child_of(c, module, graph)]
            mod_functions = [f for f in function_nodes if self._is_child_of(f, module, graph)]
            mod_methods = [m for m in method_nodes if self._is_child_of(m, module, graph)]
            mod_datamodels = [d for d in datamodel_nodes if self._is_child_of(d, module, graph)]
            files[file_path] = self._generate_module_file(
                graph, mod_classes, mod_functions, mod_methods, mod_datamodels
            )

        orphans = [
            n for n in class_nodes + function_nodes + datamodel_nodes
            if not any(self._is_child_of(n, m, graph) for m in module_nodes)
        ]
        if orphans:
            file_path = f"src/{self._to_kebab_case(graph.repository.name)}.ts"
            if file_path not in files:
                files[file_path] = self._generate_single_file(
                    graph, orphans, [], [], []
                )

        return files

    def _classify_nodes(self, graph: SoftwareGraph) -> dict[NodeType, list[SGIRNode]]:
        classified: dict[NodeType, list[SGIRNode]] = {}
        for layer_graph in graph.layers.values():
            for node in layer_graph.nodes:
                classified.setdefault(node.node_type, []).append(node)
        return classified

    def _is_child_of(self, child: SGIRNode, parent: SGIRNode, graph: SoftwareGraph) -> bool:
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

    def _to_kebab_case(self, name: str) -> str:
        return name.replace("_", "-").replace(" ", "-").replace(".", "-").lower()

    def _to_pascal_case(self, name: str) -> str:
        parts = name.replace("-", " ").replace("_", " ").split()
        return "".join(p.capitalize() for p in parts)

    def _to_camel_case(self, name: str) -> str:
        pascal = self._to_pascal_case(name)
        if not pascal:
            return pascal
        return pascal[0].lower() + pascal[1:]

    def _node_to_file_path(self, node: SGIRNode) -> str:
        if node.source_location:
            return node.source_location.file_path
        name = self._to_kebab_case(node.name)
        return f"src/{name}.ts"

    def _generate_single_file(
        self,
        graph: SoftwareGraph,
        classes: list[SGIRNode],
        functions: list[SGIRNode],
        methods: list[SGIRNode],
        datamodels: list[SGIRNode],
    ) -> str:
        sections: list[str] = []
        imports = self._collect_imports(graph)
        if imports:
            sections.append("\n".join(imports))
        for dm in datamodels:
            sections.append(self._generate_interface(dm))
        for cls in classes:
            sections.append(self._generate_class(cls, methods, graph))
        for func in functions:
            if func.node_type != NodeType.METHOD:
                sections.append(self._generate_function(func))
        return self.format_code("\n\n".join(sections))

    def _generate_module_file(
        self,
        graph: SoftwareGraph,
        classes: list[SGIRNode],
        functions: list[SGIRNode],
        methods: list[SGIRNode],
        datamodels: list[SGIRNode],
    ) -> str:
        sections: list[str] = []
        imports = self._collect_imports(graph)
        if imports:
            sections.append("\n".join(imports))
        for dm in datamodels:
            sections.append(self._generate_interface(dm))
        for cls in classes:
            sections.append(self._generate_class(cls, methods, graph))
        for func in functions:
            if func.node_type != NodeType.METHOD:
                sections.append(self._generate_exported_function(func))
        return self.format_code("\n\n".join(sections))

    def _generate_interface(self, node: SGIRNode) -> str:
        type_name = self._to_pascal_case(node.name)
        parts = [f"export interface {type_name} {{"]
        for inp in node.inputs:
            field = self._to_ts_field(inp)
            if field:
                parts.append(f"  {field};")
        parts.append("}")
        return "\n".join(parts)

    def _generate_class(
        self, cls: SGIRNode, all_methods: list[SGIRNode], graph: SoftwareGraph
    ) -> str:
        type_name = self._to_pascal_case(cls.name)
        parts = [f"export class {type_name} {{"]
        if cls.purpose:
            parts.append(f"  /** {cls.purpose} */")
        for inp in cls.inputs:
            field = self._to_ts_field(inp)
            if field:
                parts.append(f"  private {field};")
        class_methods = [m for m in all_methods if self._is_child_of(m, cls, graph)]
        if class_methods:
            parts.append("")
            for method in class_methods:
                parts.append(self._generate_class_method(method))
                parts.append("")
        parts.append("}")
        return "\n".join(parts)

    def _generate_class_method(self, method: SGIRNode) -> str:
        method_name = self._to_camel_case(method.name)
        params = self._to_ts_params(method)
        returns = self._to_ts_return_type(method)
        sig = f"  {method_name}({params}){returns} {{"
        body = indent(self._generate_body_ts(method), "    ")
        return f"{sig}\n{body}\n  }}"

    def _generate_function(self, func: SGIRNode) -> str:
        func_name = self._to_camel_case(func.name)
        params = self._to_ts_params(func)
        returns = self._to_ts_return_type(func)
        sig = f"function {func_name}({params}){returns} {{"
        body = self._generate_body_ts(func)
        return f"{sig}\n{body}\n}}"

    def _generate_exported_function(self, func: SGIRNode) -> str:
        func_name = self._to_camel_case(func.name)
        params = self._to_ts_params(func)
        returns = self._to_ts_return_type(func)
        sig = f"export function {func_name}({params}){returns} {{"
        body = self._generate_body_ts(func)
        return f"{sig}\n{body}\n}}"

    def _to_ts_params(self, node: SGIRNode) -> str:
        params = []
        for inp in node.inputs:
            parts = inp.split(":")
            name = parts[0].strip().replace("-", "_")
            if len(parts) > 1:
                ts_type = self._map_ts_type(parts[1].strip())
                params.append(f"{name}: {ts_type}")
            else:
                params.append(f"{name}: any")
        return ", ".join(params)

    def _to_ts_return_type(self, node: SGIRNode) -> str:
        if not node.outputs:
            return "void"
        if len(node.outputs) == 1:
            return self._map_ts_type(node.outputs[0].strip())
        types = " | ".join(self._map_ts_type(o.strip()) for o in node.outputs)
        return f"[{types}]"

    def _to_ts_field(self, inp: str) -> str:
        parts = inp.split(":")
        name = parts[0].strip().replace("-", "_")
        if len(parts) > 1:
            ts_type = self._map_ts_type(parts[1].strip())
            return f"{name}: {ts_type}"
        return f"{name}: any"

    def _map_ts_type(self, type_hint: str) -> str:
        mapping = {
            "str": "string",
            "string": "string",
            "int": "number",
            "int64": "number",
            "float": "number",
            "float64": "number",
            "bool": "boolean",
            "bytes": "Uint8Array",
            "list": "any[]",
            "dict": "Record<string, any>",
            "any": "any",
            "None": "void",
            "void": "void",
        }
        return mapping.get(type_hint, self._to_pascal_case(type_hint))

    def _collect_imports(self, graph: SoftwareGraph) -> list[str]:
        seen: set[str] = set()
        imports: list[str] = []
        for layer_graph in graph.layers.values():
            for edge in layer_graph.edges:
                if edge.edge_type.value == "import":
                    source_node = graph.find_node(edge.source)
                    if source_node and source_node.name not in seen:
                        seen.add(source_node.name)
                        imports.append(f'import {{ {self._to_pascal_case(source_node.name)} }} from "{source_node.name}";')
        return imports

    def _generate_body_ts(self, node: SGIRNode) -> str:
        return "  throw new Error('Not implemented');"
