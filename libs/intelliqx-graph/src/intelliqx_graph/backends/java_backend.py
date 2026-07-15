from __future__ import annotations

from textwrap import indent

from intelliqx_graph.backends.base import CodeBackend
from intelliqx_graph.models import (
    NodeType,
    SGIRNode,
    SoftwareGraph,
)


class JavaBackend(CodeBackend):
    @property
    def language(self) -> str:
        return "java"

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
            pkg = self.to_java_package(graph.repository.name)
            file_path = f"src/main/java/{pkg.replace('.', '/')}/{self.to_pascal_case(graph.repository.name)}.java"
            files[file_path] = self.generate_single_file(
                graph, pkg, class_nodes, function_nodes, method_nodes, datamodel_nodes
            )
            return files

        for pkg_node in package_nodes:
            pkg = self.to_java_package(pkg_node.name)
            pkg_classes = [c for c in class_nodes if self.is_child_of(c, pkg_node, graph)]
            pkg_functions = [f for f in function_nodes if self.is_child_of(f, pkg_node, graph)]
            pkg_methods = [m for m in method_nodes if self.is_child_of(m, pkg_node, graph)]
            pkg_datamodels = [d for d in datamodel_nodes if self.is_child_of(d, pkg_node, graph)]

            for cls in pkg_classes:
                file_path = f"src/main/java/{pkg.replace('.', '/')}/{self.to_pascal_case(cls.name)}.java"
                cls_methods = [m for m in pkg_methods if self.is_child_of(m, cls, graph)]
                files[file_path] = self.generate_class_file(
                    graph, pkg, cls, cls_methods
                )

            for dm in pkg_datamodels:
                file_path = f"src/main/java/{pkg.replace('.', '/')}/{self.to_pascal_case(dm.name)}.java"
                files[file_path] = self.generate_record_file(graph, pkg, dm)

            if pkg_functions and not pkg_classes:
                file_path = f"src/main/java/{pkg.replace('.', '/')}/{self.to_pascal_case(graph.repository.name)}App.java"
                files[file_path] = self.generate_utility_class(
                    graph, pkg, pkg_functions
                )

        orphans_cls = [
            c for c in class_nodes
            if not any(self.is_child_of(c, p, graph) for p in package_nodes)
        ]
        for cls in orphans_cls:
            pkg = self.to_java_package(graph.repository.name)
            file_path = f"src/main/java/{pkg.replace('.', '/')}/{self.to_pascal_case(cls.name)}.java"
            if file_path not in files:
                orphans_methods = [
                    m for m in method_nodes if self.is_child_of(m, cls, graph)
                ]
                files[file_path] = self.generate_class_file(
                    graph, pkg, cls, orphans_methods
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

    def to_java_package(self, name: str) -> str:
        return name.replace("-", "").replace("_", "").replace(" ", "").replace(".", "").lower()

    def to_pascal_case(self, name: str) -> str:
        parts = name.replace("-", " ").replace("_", " ").split()
        return "".join(p.capitalize() for p in parts)

    def to_camel_case(self, name: str) -> str:
        pascal = self.to_pascal_case(name)
        if not pascal:
            return pascal
        return pascal[0].lower() + pascal[1:]

    def generate_single_file(
        self,
        graph: SoftwareGraph,
        pkg: str,
        classes: list[SGIRNode],
        functions: list[SGIRNode],
        methods: list[SGIRNode],
        datamodels: list[SGIRNode],
    ) -> str:
        sections: list[str] = [f"package {pkg};"]
        imports = self.collect_imports(graph)
        if imports:
            sections.append("\n".join(imports))
        for dm in datamodels:
            sections.append(self.generate_record(graph, pkg, dm))
        for cls in classes:
            cls_methods = [m for m in methods if self.is_child_of(m, cls, graph)]
            sections.append(self.generate_class(graph, pkg, cls, cls_methods))
        if functions:
            class_name = self.to_pascal_case(graph.repository.name) + "App"
            sections.append(self.generate_utility_class_body(pkg, class_name, functions))
        return self.format_code("\n\n".join(sections))

    def generate_class_file(
        self,
        graph: SoftwareGraph,
        pkg: str,
        cls: SGIRNode,
        methods: list[SGIRNode],
    ) -> str:
        sections: list[str] = [f"package {pkg};"]
        imports = self.collect_imports(graph)
        if imports:
            sections.append("\n".join(imports))
        sections.append(self.generate_class(graph, pkg, cls, methods))
        return self.format_code("\n\n".join(sections))

    def generate_record_file(
        self,
        graph: SoftwareGraph,
        pkg: str,
        dm: SGIRNode,
    ) -> str:
        sections: list[str] = [f"package {pkg};"]
        imports = self.collect_imports(graph)
        if imports:
            sections.append("\n".join(imports))
        sections.append(self.generate_record(graph, pkg, dm))
        return self.format_code("\n\n".join(sections))

    def generate_class(
        self,
        graph: SoftwareGraph,
        pkg: str,
        cls: SGIRNode,
        methods: list[SGIRNode],
    ) -> str:
        class_name = self.to_pascal_case(cls.name)
        parts = [f"public class {class_name} {{"]
        if cls.purpose:
            parts.append(f"    /** {cls.purpose} */")
        for inp in cls.inputs:
            field = self.to_java_field(inp)
            if field:
                parts.append(f"    private {field};")
        if cls.inputs:
            parts.append("")
            params = ", ".join(self.to_java_constructor_param(f) for f in cls.inputs)
            assignments = "\n".join(
                f"        this.{self.to_camel_case(f.split(':')[0].strip())} = {self.to_camel_case(f.split(':')[0].strip())};"
                for f in cls.inputs
            )
            parts.append(f"    public {class_name}({params}) {{")
            parts.append(assignments)
            parts.append("    }")
        for method in methods:
            parts.append("")
            parts.append(self.generate_method(method))
        parts.append("}")
        return "\n".join(parts)

    def generate_record(
        self,
        graph: SoftwareGraph,
        pkg: str,
        dm: SGIRNode,
    ) -> str:
        record_name = self.to_pascal_case(dm.name)
        params = ", ".join(self.to_java_record_param(f) for f in dm.inputs)
        parts = [f"public record {record_name}({params}) {{}}"]
        return "\n".join(parts)

    def generate_utility_class(
        self,
        graph: SoftwareGraph,
        pkg: str,
        functions: list[SGIRNode],
    ) -> str:
        class_name = self.to_pascal_case(graph.repository.name) + "App"
        return self.generate_utility_class_body(pkg, class_name, functions)

    def generate_utility_class_body(
        self,
        pkg: str,
        class_name: str,
        functions: list[SGIRNode],
    ) -> str:
        parts = [f"package {pkg};", "", f"public final class {class_name} {{"]
        parts.append(f"    private {class_name}() {{}}")
        for func in functions:
            parts.append("")
            parts.append(self.generate_static_method(func))
        parts.append("}")
        return "\n".join(parts)

    def generate_method(self, method: SGIRNode) -> str:
        method_name = self.to_camel_case(method.name)
        params = self.to_java_params(method)
        returns = self.to_java_return_type(method)
        sig = f"    public {returns} {method_name}({params}) {{"
        body = indent(self.generate_body_java(method), "        ")
        return f"{sig}\n{body}\n    }}"

    def generate_static_method(self, func: SGIRNode) -> str:
        func_name = self.to_camel_case(func.name)
        params = self.to_java_params(func)
        returns = self.to_java_return_type(func)
        sig = f"    public static {returns} {func_name}({params}) {{"
        body = indent(self.generate_body_java(func), "        ")
        return f"{sig}\n{body}\n    }}"

    def to_java_params(self, node: SGIRNode) -> str:
        params = []
        for inp in node.inputs:
            parts = inp.split(":")
            name = self.to_camel_case(parts[0].strip())
            if len(parts) > 1:
                java_type = self.map_java_type(parts[1].strip())
                params.append(f"{java_type} {name}")
            else:
                params.append(f"Object {name}")
        return ", ".join(params)

    def to_java_return_type(self, node: SGIRNode) -> str:
        if not node.outputs:
            return "void"
        if len(node.outputs) == 1:
            return self.map_java_type(node.outputs[0].strip())
        return "Object"

    def to_java_field(self, inp: str) -> str:
        parts = inp.split(":")
        name = self.to_camel_case(parts[0].strip())
        if len(parts) > 1:
            java_type = self.map_java_type(parts[1].strip())
            return f"{java_type} {name}"
        return f"Object {name}"

    def to_java_constructor_param(self, inp: str) -> str:
        return self.to_java_field(inp)

    def to_java_record_param(self, inp: str) -> str:
        return self.to_java_field(inp)

    def map_java_type(self, type_hint: str) -> str:
        mapping = {
            "str": "String",
            "string": "String",
            "int": "int",
            "int64": "long",
            "float": "float",
            "float64": "double",
            "bool": "boolean",
            "bytes": "byte[]",
            "list": "List<Object>",
            "dict": "Map<String, Object>",
            "any": "Object",
            "None": "void",
            "void": "void",
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
                        imports.append(f"import {source_node.name};")
        return imports

    def generate_body_java(self, node: SGIRNode) -> str:
        return "throw new UnsupportedOperationException();"
