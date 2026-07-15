from __future__ import annotations

from textwrap import indent

from intelliqx_graph.backends.base import CodeBackend
from intelliqx_graph.models import (
    NodeType,
    SGIRNode,
    SoftwareGraph,
)


class RustBackend(CodeBackend):
    @property
    def language(self) -> str:
        return "rust"

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
            crate_name = self.to_snake_case(graph.repository.name)
            file_path = f"src/{crate_name}.rs"
            files[file_path] = self.generate_single_file(
                graph, class_nodes, function_nodes, method_nodes, datamodel_nodes
            )
            mod_path = "src/lib.rs"
            files[mod_path] = self.generate_lib_rs(crate_name)
            return files

        for module in module_nodes:
            file_path = self.node_to_file_path(module)
            mod_classes = [c for c in class_nodes if self.is_child_of(c, module, graph)]
            mod_functions = [f for f in function_nodes if self.is_child_of(f, module, graph)]
            mod_methods = [m for m in method_nodes if self.is_child_of(m, module, graph)]
            mod_datamodels = [d for d in datamodel_nodes if self.is_child_of(d, module, graph)]
            files[file_path] = self.generate_module_file(
                graph, mod_classes, mod_functions, mod_methods, mod_datamodels
            )

        orphans = [
            n for n in class_nodes + function_nodes + datamodel_nodes
            if not any(self.is_child_of(n, m, graph) for m in module_nodes)
        ]
        if orphans:
            crate_name = self.to_snake_case(graph.repository.name)
            file_path = f"src/{crate_name}.rs"
            if file_path not in files:
                files[file_path] = self.generate_single_file(
                    graph, orphans, [], [], []
                )

        mod_files = [f for f in files if f.startswith("src/") and f != "src/lib.rs"]
        if mod_files:
            mod_names = [f.replace("src/", "").replace(".rs", "") for f in mod_files]
            lines = [f"pub mod {name};" for name in mod_names]
            files["src/lib.rs"] = "\n".join(lines)

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

    def to_snake_case(self, name: str) -> str:
        return name.replace("-", "_").replace(".", "_").replace(" ", "_").lower()

    def to_pascal_case(self, name: str) -> str:
        parts = name.replace("-", " ").replace("_", " ").split()
        return "".join(p.capitalize() for p in parts)

    def node_to_file_path(self, node: SGIRNode) -> str:
        if node.source_location:
            return node.source_location.file_path
        name = self.to_snake_case(node.name)
        return f"src/{name}.rs"

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
            sections.append(self.generate_struct(dm))
        for cls in classes:
            sections.append(self.generate_struct(cls))
            impl_block = self.generate_impl_block(cls, methods, graph)
            if impl_block:
                sections.append(impl_block)
        for func in functions:
            if func.node_type != NodeType.METHOD:
                sections.append(self.generate_function(func))
        return self.format_code("\n\n".join(sections))

    def generate_module_file(
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
            sections.append(self.generate_struct(dm))
        for cls in classes:
            sections.append(self.generate_struct(cls))
            impl_block = self.generate_impl_block(cls, methods, graph)
            if impl_block:
                sections.append(impl_block)
        for func in functions:
            if func.node_type != NodeType.METHOD:
                sections.append(self.generate_function(func))
        if not sections:
            sections.append("")
        return self.format_code("\n\n".join(sections))

    def generate_lib_rs(self, crate_name: str) -> str:
        return f"pub mod {crate_name};"

    def generate_struct(self, node: SGIRNode) -> str:
        type_name = self.to_pascal_case(node.name)
        parts = [f"pub struct {type_name} {{"]
        for inp in node.inputs:
            field = self.to_rust_field(inp)
            if field:
                parts.append(f"    pub {field},")
        parts.append("}")
        return "\n".join(parts)

    def generate_impl_block(
        self, cls: SGIRNode, methods: list[SGIRNode], graph: SoftwareGraph
    ) -> str:
        type_name = self.to_pascal_case(cls.name)
        class_methods = [m for m in methods if self.is_child_of(m, cls, graph)]
        if not class_methods:
            return ""
        parts = [f"impl {type_name} {{"]
        for method in class_methods:
            parts.append(self.generate_method(method))
            parts.append("")
        parts.append("}")
        return "\n".join(parts)

    def generate_function(self, func: SGIRNode) -> str:
        func_name = self.to_snake_case(func.name)
        params = self.to_rust_params(func)
        returns = self.to_rust_returns(func)
        sig = f"pub fn {func_name}({params}){returns} {{"
        body = self.generate_body_rust(func)
        return f"{sig}\n{body}\n}}"

    def generate_method(self, method: SGIRNode) -> str:
        method_name = self.to_snake_case(method.name)
        params = self.to_rust_params(method, add_self=True)
        returns = self.to_rust_returns(method)
        sig = f"    pub fn {method_name}({params}){returns} {{"
        body = indent(self.generate_body_rust(method), "    ")
        return f"{sig}\n{body}\n    }}"

    def to_rust_params(self, node: SGIRNode, add_self: bool = False) -> str:
        params = ["&mut self"] if add_self else []
        for inp in node.inputs:
            parts = inp.split(":")
            name = parts[0].strip().replace("-", "_")
            if len(parts) > 1:
                rust_type = self.map_rust_type(parts[1].strip())
                params.append(f"{name}: {rust_type}")
            else:
                params.append(f"{name}: impl std::fmt::Debug")
        return ", ".join(params)

    def to_rust_returns(self, node: SGIRNode) -> str:
        if not node.outputs:
            return ""
        if len(node.outputs) == 1:
            return f" -> {self.map_rust_type(node.outputs[0].strip())}"
        types = ", ".join(self.map_rust_type(o.strip()) for o in node.outputs)
        return f" -> ({types})"

    def to_rust_field(self, inp: str) -> str:
        parts = inp.split(":")
        name = self.to_snake_case(parts[0].strip())
        if len(parts) > 1:
            rust_type = self.map_rust_type(parts[1].strip())
            return f"{name}: {rust_type}"
        return f"{name}: ()"

    def map_rust_type(self, type_hint: str) -> str:
        mapping = {
            "str": "String",
            "string": "String",
            "int": "i64",
            "int64": "i64",
            "float": "f64",
            "float64": "f64",
            "bool": "bool",
            "bytes": "Vec<u8>",
            "list": "Vec<Box<dyn std::any::Any>>",
            "dict": "std::collections::HashMap<String, Box<dyn std::any::Any>>",
            "any": "Box<dyn std::any::Any>",
            "None": "()",
            "void": "()",
        }
        return mapping.get(type_hint, self.to_pascal_case(type_hint))

    def collect_imports(self, graph: SoftwareGraph) -> list[str]:
        seen: set[str] = set()
        imports: list[str] = []
        for layer_graph in graph.layers.values():
            for edge in layer_graph.edges:
                if edge.edge_type.value == "import":
                    source_node = graph.find_node(edge.source)
                    if source_node and source_node.name not in seen:
                        seen.add(source_node.name)
                        imports.append(f"use {source_node.name};")
        return imports

    def generate_body_rust(self, node: SGIRNode) -> str:
        return "    todo!()"
