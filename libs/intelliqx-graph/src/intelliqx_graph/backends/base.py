from __future__ import annotations

from abc import ABC, abstractmethod

from intelliqx_graph.models import SoftwareGraph


class CodeBackend(ABC):
    @property
    @abstractmethod
    def language(self) -> str: ...

    @abstractmethod
    def generate(self, graph: SoftwareGraph) -> dict[str, str]: ...

    def format_code(self, code: str) -> str:
        return code
