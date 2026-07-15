from __future__ import annotations

from intelliqx_graph.backends.base import CodeBackend
from intelliqx_graph.backends.go_backend import GoBackend
from intelliqx_graph.backends.java_backend import JavaBackend
from intelliqx_graph.backends.python_backend import PythonBackend
from intelliqx_graph.backends.rust_backend import RustBackend
from intelliqx_graph.backends.typescript_backend import TypeScriptBackend

__all__ = [
    "CodeBackend",
    "GoBackend",
    "JavaBackend",
    "PythonBackend",
    "RustBackend",
    "TypeScriptBackend",
    "get_backend",
]

BACKENDS: dict[str, type[CodeBackend]] = {
    "python": PythonBackend,
    "go": GoBackend,
    "rust": RustBackend,
    "typescript": TypeScriptBackend,
    "java": JavaBackend,
}


def get_backend(language: str) -> CodeBackend:
    key = language.lower().strip()
    cls = BACKENDS.get(key)
    if cls is None:
        raise ValueError(
            f"Unknown language {language!r}. "
            f"Available: {', '.join(sorted(BACKENDS))}"
        )
    return cls()
