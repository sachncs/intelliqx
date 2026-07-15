"""Tests for Python parser."""

from __future__ import annotations

import textwrap
from pathlib import Path

from intelliqx_graph.parsers.python_parser import PythonParser


class TestPythonParser:
    def setup_method(self) -> None:
        self.parser = PythonParser()

    def test_language(self) -> None:
        assert self.parser.language == "python"

    def test_supported_extensions(self) -> None:
        assert ".py" in self.parser.supported_extensions()

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

    def test_syntax_error_returns_empty(self, tmp_path: Path) -> None:
        file = tmp_path / "bad.py"
        file.write_text("def broken(:\n")
        entities = self.parser.parse_file(file)
        assert entities == []

    def test_parse_files_multiple(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("def a(): pass\n")
        (tmp_path / "b.py").write_text("def b(): pass\n")
        result = self.parser.parse_files([tmp_path / "a.py", tmp_path / "b.py"])
        assert result.files_parsed == 2
        assert len(result.entities) == 2
        assert result.errors == []
