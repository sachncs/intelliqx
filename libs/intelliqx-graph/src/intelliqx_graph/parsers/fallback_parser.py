"""Regex-based fallback parser.

Provides a language-agnostic parser that uses regular expressions
to extract function and class definitions from source files.
Used when no tree-sitter grammar is available for a language.
"""

from __future__ import annotations

import re
from pathlib import Path

from intelliqx_graph.parsers import BaseParser, ParsedEntity

_FUNCTION_PATTERNS = [
    re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE),
    re.compile(r"^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)", re.MULTILINE),
    re.compile(r"^(?:public|private|protected|static|\s)*(?:[\w<>\[\], ?]+)\s+(\w+)\s*\(([^)]*)\)\s*(?:\{|->)", re.MULTILINE),
    re.compile(r"^(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>", re.MULTILINE),
    re.compile(r"^(\w+)\s*=\s*(?:async\s+)?function\s*\(([^)]*)\)", re.MULTILINE),
    re.compile(r"def\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE),
    re.compile(r"func(?:tion)?\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE),
]

_CLASS_PATTERNS = [
    re.compile(r"^(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w, ]+))?", re.MULTILINE),
    re.compile(r"^(?:pub\s+)?struct\s+(\w+)(?:<[^>]*>)?(?:\s*\{|\s*\()", re.MULTILINE),
    re.compile(r"^(?:pub\s+)?trait\s+(\w+)", re.MULTILINE),
    re.compile(r"^interface\s+(\w+)(?:\s+extends\s+([\w, ]+))?", re.MULTILINE),
    re.compile(r"^enum\s+(\w+)", re.MULTILINE),
]

_IMPORT_PATTERNS = [
    re.compile(r"^import\s+(?:\{([^}]+)\}|(\w+))\s+from\s+['\"]([^'\"]+)['\"]", re.MULTILINE),
    re.compile(r"^import\s+['\"]([^'\"]+)['\"]", re.MULTILINE),
    re.compile(r'^require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', re.MULTILINE),
    re.compile(r'^(?:use|from)\s+(\w+(?:::\w+)*)', re.MULTILINE),
]


def _estimate_complexity_from_text(source: str) -> str:
    complexity = 1
    keywords = ["if", "else if", "elif", "while", "for", "switch", "case", "catch", "except"]
    for keyword in keywords:
        complexity += len(re.findall(rf"\b{keyword}\b", source))

    if complexity <= 1:
        return "O(1)"
    elif complexity <= 3:
        return "O(n)"
    elif complexity <= 6:
        return "O(n log n)"
    elif complexity <= 10:
        return "O(n^2)"
    else:
        return "O(n^3)"


class FallbackParser(BaseParser):
    """Regex-based fallback parser for unsupported languages."""

    @property
    def language(self) -> str:
        return "fallback"

    def supported_extensions(self) -> list[str]:
        return []

    def parse_file(self, file_path: Path) -> list[ParsedEntity]:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        entities: list[ParsedEntity] = []
        file_str = str(file_path)
        lines = source.split("\n")

        for pattern in _CLASS_PATTERNS:
            for match in pattern.finditer(source):
                line_num = source[:match.start()].count("\n") + 1
                name = match.group(1)
                bases: list[str] = []
                if match.lastindex and match.lastindex >= 2 and match.group(2):
                    bases.extend(b.strip() for b in match.group(2).split(","))
                if match.lastindex and match.lastindex >= 3 and match.group(3):
                    bases.extend(b.strip() for b in match.group(3).split(","))

                end_line = line_num
                brace_count = 0
                found_open = False
                for i in range(line_num - 1, min(line_num + 500, len(lines))):
                    for ch in lines[i]:
                        if ch == "{":
                            brace_count += 1
                            found_open = True
                        elif ch == "}":
                            brace_count -= 1
                    if found_open and brace_count <= 0:
                        end_line = i + 1
                        break

                entities.append(ParsedEntity(
                    name=name,
                    entity_type="class",
                    file_path=file_str,
                    line_start=line_num,
                    line_end=end_line,
                    language="fallback",
                    bases=bases,
                    complexity=_estimate_complexity_from_text("\n".join(lines[line_num - 1:end_line])),
                ))

        for pattern in _FUNCTION_PATTERNS:
            for match in pattern.finditer(source):
                line_num = source[:match.start()].count("\n") + 1
                name = match.group(1)
                params_str = match.group(2) if match.lastindex >= 2 else ""
                params = [p.strip().split(":")[0].strip().split("=")[0].strip() for p in params_str.split(",") if p.strip()]

                end_line = line_num
                brace_count = 0
                found_open = False
                for i in range(line_num - 1, min(line_num + 500, len(lines))):
                    for ch in lines[i]:
                        if ch == "{":
                            brace_count += 1
                            found_open = True
                        elif ch == "}":
                            brace_count -= 1
                    if found_open and brace_count <= 0:
                        end_line = i + 1
                        break

                func_source = "\n".join(lines[line_num - 1:end_line])
                is_async = "async" in match.group(0).lower()

                entities.append(ParsedEntity(
                    name=name,
                    entity_type="function",
                    file_path=file_str,
                    line_start=line_num,
                    line_end=end_line,
                    language="fallback",
                    parameters=params,
                    is_async=is_async,
                    complexity=_estimate_complexity_from_text(func_source),
                ))

        for pattern in _IMPORT_PATTERNS:
            for match in pattern.finditer(source):
                line_num = source[:match.start()].count("\n") + 1
                if pattern == _IMPORT_PATTERNS[0]:
                    import_source = match.group(3)
                    import_names = [n.strip() for n in match.group(1).split(",")] if match.group(1) else [match.group(2)]
                    is_from = True
                elif pattern == _IMPORT_PATTERNS[1] or pattern == _IMPORT_PATTERNS[2]:
                    import_source = match.group(1)
                    import_names = [import_source.split("/")[-1].split(".")[-1]]
                    is_from = False
                else:
                    import_source = match.group(1)
                    import_names = [import_source.split("::")[-1]]
                    is_from = False

                entities.append(ParsedEntity(
                    name=f"from_{import_source}",
                    entity_type="import",
                    file_path=file_str,
                    line_start=line_num,
                    line_end=line_num,
                    language="fallback",
                    import_source=import_source,
                    import_names=import_names,
                    is_from_import=is_from,
                ))

        return entities
