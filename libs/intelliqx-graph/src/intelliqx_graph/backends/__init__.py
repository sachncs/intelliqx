from __future__ import annotations

from intelliqx_graph.backends.base import CodeBackend
from intelliqx_graph.backends.python_backend import PythonBackend

__all__ = ["BACKENDS", "CodeBackend", "PythonBackend", "get_backend"]

BACKENDS: dict[str, type[CodeBackend]] = {"python": PythonBackend}


def get_backend(language: str) -> CodeBackend:
    key = language.lower().strip()
    cls = BACKENDS.get(key)
    if cls is None:
        raise ValueError(
            f"Unknown language {language!r}. " f"Available: {', '.join(sorted(BACKENDS))}"
        )
    return cls()
