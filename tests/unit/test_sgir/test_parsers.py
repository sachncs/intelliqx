"""Tests for the Python parser and its end-to-end SGIR builder path."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from intelliqx_graph.optimization.layers import create_default_registry
from intelliqx_graph.parsers import ParsedEntity
from intelliqx_graph.parsers.python_parser import PythonParser


def _by_name(entities: list[ParsedEntity], name: str) -> ParsedEntity:
    matches = [e for e in entities if e.name == name]
    assert matches, f"missing entity {name!r} in {[e.name for e in entities]}"
    return matches[0]


class TestPythonParser:
    def setup_method(self) -> None:
        self.parser = PythonParser()

    def test_language(self) -> None:
        assert self.parser.language == "python"

    def test_supported_extensions(self) -> None:
        assert ".py" in self.parser.supported_extensions()
        assert ".pyi" in self.parser.supported_extensions()

    def test_parse_function(self, tmp_path: Path) -> None:
        code = textwrap.dedent("""\
            def hello(name: str) -> str:
                return f"Hello, {name}!"
        """)
        file = tmp_path / "test.py"
        file.write_text(code)
        entities = self.parser.parse_file(file)
        assert len(entities) == 1
        assert entities[0].name == "hello"
        assert entities[0].entity_type == "function"
        assert "name: str" in entities[0].parameters
        assert entities[0].return_type == "str"

    def test_parse_class(self, tmp_path: Path) -> None:
        code = textwrap.dedent("""\
            class MyClass:
                def method(self) -> None:
                    pass
        """)
        file = tmp_path / "test.py"
        file.write_text(code)
        entities = self.parser.parse_file(file)
        names = {e.name for e in entities}
        assert "MyClass" in names
        assert "method" in names

    def test_parse_import(self, tmp_path: Path) -> None:
        code = textwrap.dedent("""\
            import os
            from pathlib import Path
        """)
        file = tmp_path / "test.py"
        file.write_text(code)
        entities = self.parser.parse_file(file)
        import_entities = [e for e in entities if e.entity_type == "import"]
        assert len(import_entities) == 2

    def test_parse_async_function(self, tmp_path: Path) -> None:
        code = textwrap.dedent("""\
            async def fetch_data() -> dict:
                return {}
        """)
        file = tmp_path / "test.py"
        file.write_text(code)
        entities = self.parser.parse_file(file)
        assert entities[0].is_async is True

    def test_parse_decorated_function(self, tmp_path: Path) -> None:
        code = textwrap.dedent("""\
            @staticmethod
            def compute() -> int:
                return 42
        """)
        file = tmp_path / "test.py"
        file.write_text(code)
        entities = self.parser.parse_file(file)
        assert "staticmethod" in entities[0].decorators

    def test_syntax_error_propagates(self, tmp_path: Path) -> None:
        file = tmp_path / "bad.py"
        file.write_text("def broken(:\n")
        with pytest.raises(SyntaxError):
            self.parser.parse_file(file)

    def test_syntax_error_recorded_via_parse_files(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.py"
        bad.write_text("def broken(:\n")
        good = tmp_path / "good.py"
        good.write_text("def ok(): pass\n")
        result = self.parser.parse_files([bad, good])
        assert result.files_parsed == 1
        assert len(result.entities) == 1
        assert len(result.errors) == 1
        assert result.errors[0]["file"] == str(bad)
        assert result.errors[0]["error"]

    def test_missing_file_propagates(self, tmp_path: Path) -> None:
        result = self.parser.parse_files([tmp_path / "nope.py"])
        assert result.files_parsed == 0
        assert result.entities == []
        assert len(result.errors) == 1

    def test_parse_files_multiple(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("def a(): pass\n")
        (tmp_path / "b.py").write_text("def b(): pass\n")
        result = self.parser.parse_files([tmp_path / "a.py", tmp_path / "b.py"])
        assert result.files_parsed == 2
        assert len(result.entities) == 2
        assert result.errors == []


class TestPythonParserCoverage:
    def setup_method(self) -> None:
        self.parser = PythonParser()

    def _write(self, tmp_path: Path, name: str, code: str) -> Path:
        fp = tmp_path / name
        fp.write_text(textwrap.dedent(code))
        return fp

    def test_complete_signature(self, tmp_path: Path) -> None:
        code = '''\
            def f(x: int, /, y: int = 2, *args: str, k: int, kw: int = 3, **kwarg: bytes) -> int:
                pass
        '''
        fp = self._write(tmp_path, "sig.py", code)
        entity = _by_name(self.parser.parse_file(fp), "f")
        params = entity.parameters
        assert params[0] == "x: int"
        assert params[1] == "/"
        assert params[2] == "y: int = 2"
        assert params[3] == "*args: str"
        assert params[4] == "k: int"
        assert params[5] == "kw: int = 3"
        assert params[6] == "**kwarg: bytes"
        assert entity.return_type == "int"

    def test_decorator_dotted_and_called(self, tmp_path: Path) -> None:
        code = '''\
            @mod.deco
            @mod.deco_call(1)
            @mod.deco_subs[S](2)
            def f(): pass
        '''
        entity = _by_name(self.parser.parse_file(self._write(tmp_path, "dec.py", code)), "f")
        assert "mod.deco" in entity.decorators
        assert any(d.startswith("mod.deco_call") for d in entity.decorators)
        assert any(d.startswith("mod.deco_subs") for d in entity.decorators)

    def test_decorator_not_in_calls(self, tmp_path: Path) -> None:
        code = '''\
            @route("/x")
            def endpoint():
                helper()
        '''
        entity = _by_name(
            self.parser.parse_file(self._write(tmp_path, "route.py", code)), "endpoint"
        )
        assert any(d.startswith("route(") for d in entity.decorators)
        assert "route" not in entity.calls
        assert "helper" in entity.calls

    def test_inheritance_bases(self, tmp_path: Path) -> None:
        code = '''\
            class Base: pass
            class A(Base): pass
            class M(type): pass
            class C(A, metaclass=M, other=1):
                pass
        '''
        entities = self.parser.parse_file(self._write(tmp_path, "inh.py", code))
        c = _by_name(entities, "C")
        assert "A" in c.bases
        assert any(b.startswith("metaclass=") and "M" in b for b in c.bases)

    def test_relative_import_levels(self, tmp_path: Path) -> None:
        code = '''\
            from . import a
            from ..pkg import b as bb
            from ...mod.c import d as dd
        '''
        entities = self.parser.parse_file(self._write(tmp_path, "rel.py", code))
        imports = sorted(
            [e for e in entities if e.entity_type == "import"], key=lambda e: e.line_start
        )
        assert imports[0].import_level == 1
        assert imports[0].import_source == ""
        assert imports[0].import_names == ["a"]
        assert imports[1].import_level == 2
        assert imports[1].import_source == "pkg"
        assert imports[1].import_names == ["b"]
        assert imports[1].import_aliases == ["bb"]
        assert imports[1].name == "bb"
        assert imports[2].import_level == 3
        assert imports[2].import_source == "mod.c"
        assert imports[2].import_names == ["d"]
        assert imports[2].import_aliases == ["dd"]
        assert imports[2].name == "dd"

    def test_async_function_and_method(self, tmp_path: Path) -> None:
        code = '''\
            async def fetch():
                return 1
            class S:
                async def am(self):
                    return await fetch()
        '''
        entities = self.parser.parse_file(self._write(tmp_path, "async.py", code))
        assert _by_name(entities, "fetch").is_async is True
        assert _by_name(entities, "am").is_async is True
        assert _by_name(entities, "am").entity_type == "method"
        assert _by_name(entities, "am").parent == "S"

    def test_generator_detected(self, tmp_path: Path) -> None:
        code = '''\
            def g():
                yield 1
            def h():
                return [x for x in g()]
            def k():
                yield from g()
        '''
        entities = self.parser.parse_file(self._write(tmp_path, "gen.py", code))
        assert _by_name(entities, "g").is_generator is True
        assert _by_name(entities, "h").is_generator is False
        assert _by_name(entities, "k").is_generator is True

    def test_generator_nested_yield_does_not_mark_outer(self, tmp_path: Path) -> None:
        code = '''\
            def outer():
                def inner():
                    yield 1
                return inner

            def with_lambda():
                x = (lambda: (yield 1))

            def with_genexp():
                for i in (j for j in range(3)):
                    pass

            class C:
                cls_field = (lambda: (yield 1))
        '''
        entities = self.parser.parse_file(self._write(tmp_path, "ngen.py", code))
        assert _by_name(entities, "outer").is_generator is False
        assert _by_name(entities, "inner").is_generator is True
        assert _by_name(entities, "with_lambda").is_generator is False
        assert _by_name(entities, "with_genexp").is_generator is False
        assert _by_name(entities, "C").is_generator is False

    def test_kwonlyargs_with_bare_star(self, tmp_path: Path) -> None:
        code = '''\
            def f(*, x, y=1):
                return x + y

            def g(a, *, b, c):
                return a

            def h(*args, kw):
                pass
        '''
        entities = self.parser.parse_file(self._write(tmp_path, "kws.py", code))
        f = _by_name(entities, "f")
        g = _by_name(entities, "g")
        h = _by_name(entities, "h")
        assert f.parameters[0] == "*"
        assert "x" in f.parameters
        assert "y = 1" in f.parameters
        assert "*" in g.parameters
        assert "b" in g.parameters
        assert "c" in g.parameters
        assert h.parameters[0] == "*args"
        assert "kw" in h.parameters

    def test_class_references_populated(self, tmp_path: Path) -> None:
        code = '''\
            class C:
                x = secret_const
                CONST = validate(1)
                def m(self):
                    pass
        '''
        entities = self.parser.parse_file(self._write(tmp_path, "cls.py", code))
        c = _by_name(entities, "C")
        assert "secret_const" in c.references
        assert "validate" in c.references
        assert "x" in c.references

    def test_class_security_layer_sensitive_data(self, tmp_path: Path) -> None:
        from intelliqx_graph.models import EdgeType, GraphLayer

        code = '''\
            class UserService:
                password = "s3cret"
        '''
        entities = self.parser.parse_file(self._write(tmp_path, "sec.py", code))
        registry = create_default_registry()
        layers = registry.build_all({"entities": entities, "repository": None})
        edges = layers[GraphLayer.SECURITY].edges
        assert any(
            e.edge_type == EdgeType.DATA and e.target == "sensitive::password" for e in edges
        )

    def test_nested_defs_under_function(self, tmp_path: Path) -> None:
        code = '''\
            def outer():
                def inner():
                    def deep():
                        return deep_call()
                inner()
        '''
        entities = self.parser.parse_file(self._write(tmp_path, "nest.py", code))
        outer = _by_name(entities, "outer")
        inner = _by_name(entities, "inner")
        deep = _by_name(entities, "deep")
        assert outer.parent is None
        assert inner.parent == "outer"
        assert inner.entity_type == "function"
        assert deep.parent == "inner"
        assert deep.entity_type == "function"

    def test_nested_defs_in_control_flow_keep_outer_parent(self, tmp_path: Path) -> None:
        code = '''\
            def outer():
                if cond:
                    def helper():
                        return 1
                for x in y:
                    def loop_helper():
                        return x
        '''
        entities = self.parser.parse_file(self._write(tmp_path, "cfg.py", code))
        assert _by_name(entities, "helper").parent == "outer"
        assert _by_name(entities, "loop_helper").parent == "outer"

    def test_nested_calls_do_not_leak(self, tmp_path: Path) -> None:
        code = '''\
            def outer():
                outer_call()
                def inner():
                    inner_call()
                    deeply_nested()
                inner()
        '''
        entities = self.parser.parse_file(self._write(tmp_path, "leak.py", code))
        outer = _by_name(entities, "outer")
        inner = _by_name(entities, "inner")
        assert "outer_call" in outer.calls
        assert "inner" in outer.calls
        assert "inner_call" not in outer.calls
        assert "deeply_nested" not in outer.calls
        assert inner.calls == ["inner_call", "deeply_nested"]

    def test_method_calls_resolve_by_parent(self, tmp_path: Path) -> None:
        code = '''\
            class C:
                def m1(self):
                    self.helper()
                def helper(self):
                    pass
        '''
        entities = self.parser.parse_file(self._write(tmp_path, "mcall.py", code))
        m1 = _by_name(entities, "m1")
        assert "helper" in m1.calls
        assert "self" in m1.references

    def test_docstring(self, tmp_path: Path) -> None:
        code = '''\
            def f():
                """docstring."""
        '''
        entity = _by_name(self.parser.parse_file(self._write(tmp_path, "doc.py", code)), "f")
        assert entity.docstring == "docstring."

    def test_stable_source_locations(self, tmp_path: Path) -> None:
        code = '''\
            def f():
                return 1
            class C:
                pass
        '''
        entities = self.parser.parse_file(self._write(tmp_path, "loc.py", code))
        f = _by_name(entities, "f")
        c = _by_name(entities, "C")
        assert f.line_start == 1
        assert f.line_end == 2
        assert c.line_start == 3
        assert c.line_end == 4

    def test_deterministic_source_order(self, tmp_path: Path) -> None:
        code = '''\
            import a
            def first(): pass
            class C:
                def m(self): pass
            def second(): pass
        '''
        entity_names = [
            e.name for e in self.parser.parse_file(self._write(tmp_path, "ord.py", code))
        ]
        assert entity_names == ["a", "first", "C", "m", "second"]

    def test_deterministic_across_runs(self, tmp_path: Path) -> None:
        code = '''\
            def a(): helper()
            def b(): a()
            def helper(): return 1
        '''
        entities_1 = self.parser.parse_file(self._write(tmp_path, "det.py", code))
        entities_2 = self.parser.parse_file(self._write(tmp_path, "det.py", code))
        a_1 = [e.name for e in entities_1]
        a_2 = [e.name for e in entities_2]
        assert a_1 == a_2
        assert a_1 == ["a", "b", "helper"]

    def test_pyi_extension_supported(self, tmp_path: Path) -> None:
        fp = tmp_path / "stubs.pyi"
        fp.write_text("def iface(x: int) -> int: ...\n")
        entity = _by_name(self.parser.parse_file(fp), "iface")
        assert entity.entity_type == "function"
        assert entity.return_type == "int"

    def test_dotted_attribute_call_emits_attribute(self, tmp_path: Path) -> None:
        code = '''\
            def caller():
                mod.helper(1)
                obj.method()
        '''
        entity = _by_name(self.parser.parse_file(self._write(tmp_path, "dot.py", code)), "caller")
        assert "helper" in entity.calls
        assert "method" in entity.calls


class TestPythonParserGraphIntegration:
    def setup_method(self) -> None:
        self.parser = PythonParser()

    def test_build_layers_produces_call_data_control_edges(self, tmp_path: Path) -> None:
        code = textwrap.dedent('''\
            from fastapi import FastAPI

            app = FastAPI()

            def store(payload):
                return payload

            def validate():
                return True

            @app.get("/health")
            def health():
                return {"ok": True}

            @app.post("/items")
            def create(payload: dict) -> dict:
                if not validate():
                    raise ValueError("bad")
                if not payload:
                    raise ValueError("empty")
                store(payload)
                return payload
        ''')
        fp = tmp_path / "api.py"
        fp.write_text(code)
        entities = self.parser.parse_file(fp)
        registry = create_default_registry()
        layers = registry.build_all({"entities": entities, "repository": None})

        from intelliqx_graph.models import EdgeType, GraphLayer

        call_layer = layers[GraphLayer.CALL]
        data_layer = layers[GraphLayer.DATA_FLOW]
        control_layer = layers[GraphLayer.CONTROL_FLOW]

        assert any(e.edge_type == EdgeType.CALL for e in call_layer.edges)
        create_id = next(n.id for n in call_layer.nodes if n.name == "create")
        store_id = next(n.id for n in call_layer.nodes if n.name == "store")
        assert any(
            e.edge_type == EdgeType.CALL and e.source == create_id and e.target == store_id
            for e in call_layer.edges
        )
        assert any(e.edge_type == EdgeType.DATA for e in data_layer.edges)
        assert any(e.edge_type == EdgeType.CONTROL for e in control_layer.edges)


class TestParseRepositoryContract:
    def test_parse_repository_returns_entities_and_errors(self, tmp_path: Path) -> None:
        from intelliqx_graph.operations import parse_repository

        good = tmp_path / "good.py"
        good.write_text("def f(): pass\n")
        bad = tmp_path / "bad.py"
        bad.write_text("def broken(:\n")

        result = parse_repository(str(tmp_path))
        assert isinstance(result, dict)
        assert "entities" in result and "errors" in result
        assert isinstance(result["entities"], list)
        assert isinstance(result["errors"], list)
        assert len(result["entities"]) == 1
        assert len(result["errors"]) == 1
        assert all(isinstance(e, dict) for e in result["entities"])
        assert all(isinstance(e, dict) for e in result["errors"])

    def test_parse_repository_feeds_build_software_graph(self, tmp_path: Path) -> None:
        from intelliqx_graph.models import RepositoryMetadata
        from intelliqx_graph.operations import build_software_graph, parse_repository
        from intelliqx_graph.serialization import graph_from_json

        code = textwrap.dedent('''\
            def helper():
                return 1

            def caller():
                return helper()
        ''')
        (tmp_path / "mod.py").write_text(code)
        result = parse_repository(str(tmp_path))
        assert result["errors"] == []

        repo = RepositoryMetadata(name="t", root_path=str(tmp_path))
        graph_json = build_software_graph(repo.model_dump(mode="json"), result["entities"])
        sg = graph_from_json(graph_json)
        assert sum(g.node_count for g in sg.layers.values()) > 0


def test_self_improve_pipeline_smoke(tmp_path: Path) -> None:
    from intelliqx_graph.operations import parse_repository

    (tmp_path / "a.py").write_text("def f(): return 1\n")
    (tmp_path / "b.py").write_text("class C:\n    def m(self): return f()\n")

    parsed = parse_repository(str(tmp_path))
    assert isinstance(parsed, dict)
    assert "entities" in parsed
    assert "errors" in parsed
    assert isinstance(parsed["entities"], list)
    assert parsed["errors"] == []
    counters: dict[str, int] = {}
    for entry in parsed["entities"]:
        counters[entry["entity_type"]] = counters.get(entry["entity_type"], 0) + 1
    assert counters.get("function", 0) >= 1
    assert counters.get("class", 0) >= 1
