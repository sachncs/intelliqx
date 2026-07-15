"""Abstract base parser for all languages.

Every language parser converts source files into a list of
``ParsedEntity`` objects that the Semantic Graph Builder consumes
to construct SGIR nodes and edges.
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ParsedEntity(BaseModel):
    """A single parsed code entity (function, class, import, etc.).

    This is the intermediate representation between raw AST parsing
    and SGIR graph construction. It is language-agnostic.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    entity_type: str  # "function", "class", "method", "import", "variable", "decorator"
    file_path: str
    line_start: int
    line_end: int
    language: str

    # Parent scope (e.g., class name for a method)
    parent: str | None = None

    # For functions/methods
    parameters: list[str] = Field(default_factory=list)
    return_type: str | None = None
    is_async: bool = False
    is_generator: bool = False
    is_static: bool = False
    is_abstract: bool = False

    # For imports
    import_source: str | None = None
    import_names: list[str] = Field(default_factory=list)
    is_from_import: bool = False

    # For classes
    bases: list[str] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)

    # Calls and references (populated during cross-file analysis)
    calls: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)

    # Documentation
    docstring: str | None = None

    # Complexity estimate
    complexity: str = "unknown"


class ParseResult(BaseModel):
    """Result of parsing a set of files from one language."""

    model_config = ConfigDict(extra="forbid")

    language: str
    files_parsed: int = 0
    entities: list[ParsedEntity] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseParser(abc.ABC):
    """Abstract base class for language parsers.

    Subclasses implement ``parse_file`` and ``parse_files`` to convert
    source code into ``ParsedEntity`` objects.
    """

    @property
    @abc.abstractmethod
    def language(self) -> str:
        """The language this parser handles."""

    @abc.abstractmethod
    def parse_file(self, file_path: Path) -> list[ParsedEntity]:
        """Parse a single file into entities.

        Args:
            file_path: Absolute path to the source file.

        Returns:
            List of parsed entities found in the file.
        """
        raise NotImplementedError

    def parse_files(self, file_paths: list[Path]) -> ParseResult:
        """Parse multiple files and aggregate results.

        Args:
            file_paths: List of absolute paths to source files.

        Returns:
            A ``ParseResult`` with all entities and error info.
        """
        all_entities: list[ParsedEntity] = []
        errors: list[dict[str, str]] = []
        parsed_count = 0

        for fp in file_paths:
            try:
                entities = self.parse_file(fp)
                all_entities.extend(entities)
                parsed_count += 1
            except Exception as exc:
                errors.append({"file": str(fp), "error": str(exc)})

        return ParseResult(
            language=self.language,
            files_parsed=parsed_count,
            entities=all_entities,
            errors=errors,
        )

    def supported_extensions(self) -> list[str]:
        """Return the file extensions this parser handles."""
        return []
