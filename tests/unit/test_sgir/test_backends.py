"""Tests for code generation backends."""

from __future__ import annotations

import pytest
from intelliqx_graph.backends import get_backend
from intelliqx_graph.models import (
    EdgeType,
    GraphLayer,
    NodeType,
    RepositoryMetadata,
    SGIREdge,
    SGIRGraph,
    SGIRNode,
    SoftwareGraph,
    SourceLocation,
)


def make_test_sg() -> SoftwareGraph:
    repo = RepositoryMetadata(name="test", root_path="/tmp")
    sg = SoftwareGraph(repository=repo)

    nodes = [
        SGIRNode(
            id="mod",
            name="mymodule",
            node_type=NodeType.MODULE,
            source_location=SourceLocation(file_path="mymodule.py", line_start=1, line_end=20),
        ),
        SGIRNode(
            id="fn1",
            name="process",
            node_type=NodeType.FUNCTION,
            inputs=["data"],
            outputs=["result"],
            source_location=SourceLocation(file_path="mymodule.py", line_start=3, line_end=10),
        ),
        SGIRNode(
            id="cls1",
            name="Processor",
            node_type=NodeType.CLASS,
            source_location=SourceLocation(file_path="mymodule.py", line_start=12, line_end=20),
        ),
    ]
    edges = [
        SGIREdge(source="mod", target="fn1", edge_type=EdgeType.CALL),
        SGIREdge(source="mod", target="cls1", edge_type=EdgeType.CALL),
    ]
    sg.add_layer(SGIRGraph(layer=GraphLayer.CALL, nodes=nodes, edges=edges))
    return sg


class TestGetBackend:
    def test_python_backend(self) -> None:
        backend = get_backend("python")
        assert backend is not None
        assert backend.language == "python"

    def test_go_backend(self) -> None:
        backend = get_backend("go")
        assert backend is not None
        assert backend.language == "go"

    def test_rust_backend(self) -> None:
        backend = get_backend("rust")
        assert backend is not None
        assert backend.language == "rust"

    def test_typescript_backend(self) -> None:
        backend = get_backend("typescript")
        assert backend is not None
        assert backend.language == "typescript"

    def test_java_backend(self) -> None:
        backend = get_backend("java")
        assert backend is not None
        assert backend.language == "java"

    def test_unknown_backend(self) -> None:
        with pytest.raises(ValueError):
            get_backend("brainfuck")

    def test_available_backends(self) -> None:
        from intelliqx_graph.backends import BACKENDS
        assert "python" in BACKENDS
        assert "go" in BACKENDS


class TestPythonBackend:
    def test_generate(self) -> None:
        sg = make_test_sg()
        backend = get_backend("python")
        files = backend.generate(sg)
        assert isinstance(files, dict)
        assert len(files) > 0
        for _path, code in files.items():
            assert isinstance(code, str)
            assert len(code) > 0

    def test_generate_empty_graph(self) -> None:
        repo = RepositoryMetadata(name="empty", root_path="/tmp")
        sg = SoftwareGraph(repository=repo)
        sg.add_layer(SGIRGraph(layer=GraphLayer.CALL))
        backend = get_backend("python")
        files = backend.generate(sg)
        assert isinstance(files, dict)


class TestGoBackend:
    def test_generate(self) -> None:
        sg = make_test_sg()
        backend = get_backend("go")
        files = backend.generate(sg)
        assert isinstance(files, dict)


class TestRustBackend:
    def test_generate(self) -> None:
        sg = make_test_sg()
        backend = get_backend("rust")
        files = backend.generate(sg)
        assert isinstance(files, dict)


class TestTypeScriptBackend:
    def test_generate(self) -> None:
        sg = make_test_sg()
        backend = get_backend("typescript")
        files = backend.generate(sg)
        assert isinstance(files, dict)


class TestJavaBackend:
    def test_generate(self) -> None:
        sg = make_test_sg()
        backend = get_backend("java")
        files = backend.generate(sg)
        assert isinstance(files, dict)
