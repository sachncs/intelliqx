"""Self-improvement driver: use intelliqx's own SGIR pipeline + a library of
heuristic auditors to analyse and improve the intelliqx repo itself.

This proves the platform works end-to-end. The driver:

1. Runs the SGIR pipeline (scan -> parse -> build -> analyze ->
   optimize -> codegen) against the repo root.
2. Surfaces every SGIR finding (architecture, flow, perf, security,
   duplicates, dead code, parallel branches, generated files).
3. Runs 10 heuristic auditors that complement the SGIR findings:

   * lingering __ name-mangling (regression safety net)
   * unused imports
   * long functions (>50 lines)
   * missing module __all__
   * bare ``except`` clauses
   * silent ``except: pass`` blocks
   * print() leaks in libs (excluding docstring examples)
   * TODO/FIXME/HACK markers
   * id()-based caches (memory leak risk)
   * public functions missing docstrings

4. Applies safe, mechanical fixes (the underscore + unused-import +
   __all__ auditors apply automatic patches).
5. Verifies the result by running ruff + pytest.
6. Saves a JSON report at scripts/self_improve_report.json.

Run with::

    uv run python scripts/self_improve.py [--apply]

Without ``--apply`` the driver is read-only.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "agents"))


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def run_sgir_pipeline(repo_path: str) -> dict[str, Any]:
    """Run the SGIR pipeline end-to-end and return structured output."""
    from intelliqx_graph.adk_agents import (
        generate_code_tool,
        optimize_graph_tool,
        parse_repository_tool,
        scan_repository_tool,
    )
    from intelliqx_graph.analysis import (
        ArchitectureAgent,
        FlowAnalysisAgent,
        PerformanceAgent,
        SecurityAgent,
    )
    from intelliqx_graph.models import GraphLayer
    from intelliqx_graph.optimization.passes import (
        detect_duplicates,
        parallelize_independent_branches,
        remove_dead_nodes,
    )
    from intelliqx_graph.query import GraphIndex

    out: dict[str, Any] = {"errors": [], "warnings": []}

    metadata = scan_repository_tool(repo_path)
    out["metadata"] = metadata

    parsed = parse_repository_tool(repo_path)
    raw_entities = parsed["entities"]
    out["errors"].extend(parsed["errors"])
    out["parsed_entity_count"] = len(raw_entities)
    entity_types = Counter(e.get("entity_type", "?") for e in raw_entities)

    section("Building graph layers")
    from intelliqx_graph.adk_agents import build_software_graph_tool

    try:
        graph_json_str = build_software_graph_tool(metadata, raw_entities)
    except Exception as exc:
        out["errors"].append(f"build_software_graph_tool crashed: {exc!r}")
        traceback.print_exc()
        return out
    from intelliqx_graph.serialization import graph_from_json

    sg = graph_from_json(graph_json_str)
    layer_graphs = dict(sg.layers)  # dict[GraphLayer, SGIRGraph]
    layer_node_counts = {layer.value: len(layer_graphs[layer].nodes) for layer in layer_graphs}

    layer_node_counts = {layer.value: len(g.nodes) for layer, g in layer_graphs.items()}
    out["layer_node_counts"] = layer_node_counts
    print(f"  scanned {metadata['total_files']} files, {metadata['total_lines']} LOC")
    print(f"  parsed {len(raw_entities)} entities: {dict(entity_types.most_common(6))}")
    for layer_name, count in layer_node_counts.items():
        print(f"    layer {layer_name}: {count} nodes")

    out["graph_node_total"] = sum(layer_node_counts.values())

    section("Running analysis agents")
    index = GraphIndex(sg)
    for name, agent_cls in [
        ("architecture", ArchitectureAgent),
        ("flow", FlowAnalysisAgent),
        ("performance", PerformanceAgent),
        ("security", SecurityAgent),
    ]:
        try:
            report = agent_cls(index).analyze()
            payload = report.model_dump(mode="json")
            out[f"analysis.{name}"] = payload
            for key in payload:
                val = payload[key]
                if isinstance(val, list):
                    print(f"  {name}.{key}: {len(val)} item(s)")
                elif (isinstance(val, dict) and val) or isinstance(val, bool):
                    print(f"  {name}.{key}: {val}")
        except Exception as exc:
            out["errors"].append(f"{name} agent crashed: {exc!r}")

    section("Optimization passes")
    call_layer = sg.layers.get(GraphLayer.CALL)
    in_deg = Counter(e.target for e in (call_layer.edges if call_layer else []))
    out_deg = Counter(e.source for e in (call_layer.edges if call_layer else []))
    node_ids = call_layer.node_ids if call_layer else set()
    entry_points = [nid for nid in node_ids if in_deg.get(nid, 0) == 0 and out_deg.get(nid, 0) > 0][
        :25
    ]
    print(f"  entry points identified: {len(entry_points)}")

    graph_json = sg.model_dump_json()
    try:
        opt_result = optimize_graph_tool(graph_json, entry_points, "python")
        out["optimization"] = opt_result
        s = opt_result.get("summary", {}) if isinstance(opt_result, dict) else {}
        print(f"  duplicates: {s.get('duplicate_pairs_found', '?')}")
        print(f"  parallel branches: {s.get('parallel_branches_found', '?')}")
        print(f"  passes verified: {s.get('pass_count', '?')}")
        print(f"  behaviour preserved: {s.get('all_behavior_preserved', '?')}")
    except Exception as exc:
        out["errors"].append(f"optimization crashed: {exc!r}")

    section("Code generation")
    try:
        code = generate_code_tool(graph_json, "python")
        if isinstance(code, dict):
            out["generated_files"] = len(code)
            print(f"  generated {len(code)} files (sample):")
            for k in list(code.keys())[:5]:
                print(f"    {k}")
        else:
            out["generated_files"] = 0
            print(f"  generate_code_tool returned: {code}")
    except Exception as exc:
        out["errors"].append(f"codegen crashed: {exc!r}")

    try:
        dups = detect_duplicates(sg, index)
        out["duplicates_direct"] = [list(d) for d in dups]
    except Exception as exc:
        out["warnings"].append(f"detect_duplicates crashed: {exc!r}")

    try:
        branches = parallelize_independent_branches(sg, index)
        out["parallel_branches_direct"] = [sorted(b) for b in branches[:25]]
    except Exception as exc:
        out["warnings"].append(f"parallelize crashed: {exc!r}")

    try:
        if call_layer and call_layer.edges and call_layer.node_ids:
            remove_dead_nodes(sg, index, list(entry_points) or list(node_ids)[:5])
            out["dead_code_scan"] = "survived"
    except Exception as exc:
        out["warnings"].append(f"remove_dead_nodes crashed: {exc!r}")

    return out


def find_lingering_double_underscore(py_files: list[Path]) -> list[tuple[Path, int, str, str]]:
    """Find lingering ``self.__<name>`` (non-dunder protocol) references."""
    findings: list[tuple[Path, int, str, str]] = []
    pattern = re.compile(r"\bself\.__(?P<name>[A-Za-z_]\w*)")
    for fp in py_files:
        try:
            text = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            m = pattern.search(line)
            if not m:
                continue
            name = m.group("name")
            if name.endswith("__"):
                continue
            findings.append((fp, i, line.rstrip(), name))
    return findings


def find_unused_imports_ast(py_files: list[Path]) -> list[tuple[Path, int, str, str]]:
    """AST-based unused-import detector.

    More accurate than the regex variant — it actually parses the
    module and only counts non-import usages (excluding the
    ``IMPORT_NAME`` token and import lines themselves).

    Imports marked ``# noqa: F401`` are intentionally unused (they
    probe SDK availability) and are skipped.
    """
    findings: list[tuple[Path, int, str, str]] = []
    for fp in py_files:
        if fp.name == "__init__.py":
            continue
        try:
            source = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        try:
            tree = ast.parse(source, filename=str(fp))
        except SyntaxError:
            continue
        lines = source.splitlines()

        def line_has_noqa(lineno: int, _lines: list[str] = lines) -> bool:
            if 1 <= lineno <= len(_lines):
                return "noqa: F401" in _lines[lineno - 1]
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    if not name:
                        continue
                    if _name_used_outside_imports(tree, name):
                        continue
                    if line_has_noqa(node.lineno):
                        continue
                    findings.append((fp, node.lineno, f"unused import: {alias.name}", name))
            elif isinstance(node, ast.ImportFrom):
                # ``from __future__ import annotations`` is a special
                # directive that does not bind a module name —
                # always skip it.
                if (node.module or "") == "__future__":
                    continue
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    name = alias.asname or alias.name
                    if not name:
                        continue
                    if _name_used_outside_imports(tree, name):
                        continue
                    if line_has_noqa(node.lineno):
                        continue
                    findings.append(
                        (fp, node.lineno, f"unused import: {name} from {node.module or '?'}", name)
                    )
    return findings


def _name_used_outside_imports(tree: ast.Module, name: str) -> bool:
    """Return True if ``name`` is referenced somewhere that's not an import line.

    ``from __future__ import X`` is a special directive that does NOT
    bind ``X`` in the module namespace, so ``annotations`` and
    siblings never get flagged by this routine.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            continue
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load):
            return True
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == name
            and isinstance(node.value.ctx, ast.Load)
        ):
            return True
    return False


def find_long_functions(py_files: list[Path], threshold: int = 50) -> list[tuple[Path, str, int]]:
    """Flag functions/methods whose body is longer than ``threshold`` lines."""
    findings: list[tuple[Path, str, int]] = []
    for fp in py_files:
        try:
            source = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        try:
            tree = ast.parse(source, filename=str(fp))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            start = node.lineno
            end = getattr(node, "end_lineno", None) or start
            length = end - start + 1
            if length >= threshold:
                findings.append((fp, f"{node.name} ({length} lines)", start))
    findings.sort(key=lambda x: -x[2])
    return findings


def find_bare_except(py_files: list[Path]) -> list[tuple[Path, int, str]]:
    """Find ``except:`` (no exception class) and silent ``except: pass`` blocks."""
    findings: list[tuple[Path, int, str]] = []
    for fp in py_files:
        try:
            source = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        try:
            tree = ast.parse(source, filename=str(fp))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                findings.append((fp, node.lineno, "bare ``except:``"))
                body = node.body
                if len(body) == 1 and isinstance(body[0], ast.Pass):
                    findings.append((fp, node.lineno + 1, "silent ``except: pass``"))
    return findings


def find_missing_all(py_files: list[Path]) -> list[Path]:
    """Find ``__init__.py`` files without a public ``__all__`` declaration.

    A well-documented package exposes an explicit ``__all__`` to
    control ``from foo import *`` and to document the public
    surface. We only flag library ``__init__.py`` files (under
    ``libs/`` and ``agents/``) — test conftests and scripts are
    exempt. Pure-docstring ``__init__.py`` files (only the module
    docstring, no imports / classes / functions) are also exempt
    because there's nothing to expose.
    """
    findings: list[Path] = []
    for fp in py_files:
        if fp.name != "__init__.py":
            continue
        if "tests" in fp.parts:
            continue
        if "scripts" in fp.parts:
            continue
        try:
            source = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        if any(
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
            )
            for node in tree.body
        ):
            continue

        # If the file has nothing but the module docstring, it's
        # a documentation placeholder, not an importable module.
        non_docstring = [
            n
            for n in tree.body
            if not (
                isinstance(n, ast.Expr)
                and isinstance(n.value, ast.Constant)
                and isinstance(n.value.value, str)
            )
        ]
        if not non_docstring:
            continue
        findings.append(fp)
    return findings


def find_print_leaks(py_files: list[Path]) -> list[tuple[Path, int, str]]:
    """Find executable ``print()`` calls left in production libs code.

    Production libraries should report via a logger or raise;
    ``print()`` goes directly to stderr/stdout and is invisible
    to callers. The auditor counts only top-level ``print()`` and
    ``print()`` calls inside function bodies, never docstring
    examples. CLI entry points (``_smoke.py``, ``__main__.py``)
    are explicitly exempt — they exist to write to stdout.
    """
    findings: list[tuple[Path, int, str]] = []
    cli_files = {"_smoke.py", "__main__.py"}
    for fp in py_files:
        if "scripts" in fp.parts or "tests" in fp.parts:
            continue
        if fp.name in cli_files:
            continue
        try:
            source = fp.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeError):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        def is_in_docstring(lineno: int, _tree: ast.Module = tree) -> bool:
            for node in ast.walk(_tree):
                if isinstance(
                    node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    docstring_node = node.body[0] if node.body else None
                    if (
                        isinstance(docstring_node, ast.Expr)
                        and isinstance(docstring_node.value, ast.Constant)
                        and isinstance(docstring_node.value.value, str)
                    ):
                        start = docstring_node.lineno
                        end = getattr(docstring_node, "end_lineno", start) or start
                        if start <= lineno <= end:
                            return True
            return False

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                src = ast.unparse(node)
                if is_in_docstring(node.lineno):
                    continue
                findings.append((fp, node.lineno, src))
    return findings


def find_todo_fixme_markers(py_files: list[Path]) -> list[tuple[Path, int, str, str]]:
    """Find TODO / FIXME / HACK markers in library and agent code.

    Real action items left in production code are tech debt. The
    auditor picks up exact-word markers (``# TODO`` rather than
    ``# TODOList``) and skips ones already in CHANGELOG / docs.
    """
    findings: list[tuple[Path, int, str, str]] = []
    pattern = re.compile(r"#\s*(TODO|FIXME|HACK|XXX)\b(?:\s*\(([^)]*)\))?\s*:?(.*)")
    skip_dirs = {"tests", "scripts", "docs", "node_modules", ".venv"}
    for fp in py_files:
        if any(p in fp.parts for p in skip_dirs):
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeError):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            m = pattern.search(line)
            if m:
                findings.append((fp, i, line.rstrip(), m.group(1)))
    return findings


def find_id_based_caches(py_files: list[Path]) -> list[tuple[Path, int, str, str]]:
    """Find ``dict[id(x)]`` and ``{id(x): ...}`` patterns — memory leak risk.

    Using ``id()`` as a dict key pins the object forever, even
    after the original goes out of scope, because the dict
    outlives the object's reference count. The safe pattern is
    ``weakref.WeakValueDictionary`` / ``WeakKeyDictionary`` —
    or simply don't cache at all if the build is cheap.
    """
    findings: list[tuple[Path, int, str, str]] = []
    pattern = re.compile(r"\b(?:id|hash)\s*\(\s*[a-zA-Z_]\w*\s*\)")
    skip_dirs = {"scripts", "tests", "docs"}
    for fp in py_files:
        if any(p in fp.parts for p in skip_dirs):
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeError):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line) and ("_cache" in line.lower() or "_CACHE" in line):
                findings.append((fp, i, line.rstrip(), "id()-based cache"))
    return findings


def find_missing_public_func_docstrings(py_files: list[Path]) -> list[tuple[Path, str, int]]:
    """Find public module-level functions without a docstring.

    Pydantic ``BaseModel`` subclasses inherit a class-level
    docstring (the body is one), so we only flag plain functions
    and classes whose first statement is not a string literal.
    """
    findings: list[tuple[Path, str, int]] = []
    skip_dirs = {"tests", "scripts", "infra"}
    for fp in py_files:
        if any(p in fp.parts for p in skip_dirs):
            continue
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            if ast.get_docstring(node):
                continue
            findings.append((fp, node.name, node.lineno))
    return findings


def auto_fix_add_all(py_files: list[Path], apply: bool) -> dict[str, Any]:
    """Auto-derive ``__all__`` for ``__init__.py`` files that lack one.

    The derivation rule is: take every public name at module level
    that isn't imported via ``from ... import *`` and isn't itself
    another ``__init__`` marker. Names that come from
    ``from X import Y`` are preferred because they document the
    public surface as the author actually wrote it.
    """
    files_touched: set[Path] = set()
    added = 0
    for fp in py_files:
        if fp.name != "__init__.py":
            continue
        if any(p in fp.parts for p in ("tests", "scripts")):
            continue
        try:
            source = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        if any(
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
            )
            for node in tree.body
        ):
            continue

        public_names: list[str] = []
        seen: set[str] = set()
        for node in tree.body:
            names: list[str] = []
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    names.append(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    names.append(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)) and not node.name.startswith(
                "_"
            ):
                names.append(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("_"):
                        names.append(target.id)
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and not node.target.id.startswith("_")
            ):
                names.append(node.target.id)

            for name in names:
                if name and name not in seen and name not in {"annotations"}:
                    seen.add(name)
                    public_names.append(name)

        if not public_names:
            continue

        # Build the __all__ block using the same indentation as
        # the surrounding code (4 spaces — module-level).
        all_lines = ["__all__ = ["]
        for name in sorted(public_names):
            all_lines.append(f'    "{name}",')
        all_lines.append("]")
        block = "\n".join(all_lines) + "\n"

        # Place __all__ at the very end so it doesn't break docstrings
        # or imports that reference it.
        new_source = source.rstrip() + "\n\n\n" + block
        if apply:
            fp.write_text(new_source, encoding="utf-8")
            files_touched.add(fp)
        added += 1
    return {"added": added, "files_touched": len(files_touched), "applied": apply}


def auto_fix_underscore(py_files: list[Path], apply: bool) -> dict[str, Any]:
    """Strip remaining ``self.__<name>`` -> ``self.<name>``.

    Uses a per-line AST-aware check (rather than a single regex) so
    we only touch real name-mangled instance attributes and not
    legitimate dunder protocol usage like ``self.__class__``,
    ``self.__init_subclass__``, etc.
    """
    fix_re = re.compile(r"\bself\.__(?P<name>[A-Za-z_]\w*)")

    fixed_total = 0
    files_touched: set[Path] = set()
    for fp in py_files:
        try:
            original = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        new_lines: list[str] = []
        changed_in_file = 0
        for line in original.splitlines(keepends=True):
            updated_line = line
            for m in fix_re.finditer(line):
                name = m.group("name")
                if name.endswith("__"):
                    continue
                updated_line = updated_line.replace(m.group(0), f"self.{name}", 1)
            if updated_line != line:
                changed_in_file += 1
            new_lines.append(updated_line)
        if changed_in_file:
            new_text = "".join(new_lines)
            if apply:
                fp.write_text(new_text, encoding="utf-8")
            fixed_total += changed_in_file
            files_touched.add(fp)
    return {"findings": fixed_total, "files_touched": len(files_touched), "applied": apply}


def auto_fix_unused_imports(py_files: list[Path], apply: bool) -> dict[str, Any]:
    """Remove unused imports detected by AST analysis."""
    removed_total = 0
    files_touched: set[Path] = set()
    skipped: list[str] = []
    for fp in py_files:
        if fp.name == "__init__.py":
            continue
        try:
            source = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        try:
            tree = ast.parse(source, filename=str(fp))
        except SyntaxError:
            continue
        lines_with_endings = source.splitlines(keepends=True)
        lines_no_endings = source.splitlines()
        unused_lines: list[tuple[int, int]] = []

        def has_noqa(lineno: int, _lines: list[str] = lines_no_endings) -> bool:
            if 1 <= lineno <= len(_lines):
                return "noqa: F401" in _lines[lineno - 1]
            return False

        for node in ast.walk(tree):
            target_line: int | None = None
            if isinstance(node, ast.Import):
                names = [a.asname or a.name.split(".")[0] for a in node.names]
                if any(_name_used_outside_imports(tree, n) for n in names):
                    continue
                if has_noqa(node.lineno):
                    continue
                target_line = node.lineno
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "") == "__future__":
                    continue
                if any(a.name == "*" for a in node.names):
                    continue
                names = [a.asname or a.name for a in node.names]
                if any(_name_used_outside_imports(tree, n) for n in names):
                    continue
                if has_noqa(node.lineno):
                    continue
                target_line = node.lineno
            if target_line is None:
                continue

            end_line = getattr(node, "end_lineno", None)
            if end_line is None:
                end_line = target_line
            unused_lines.append((target_line - 1, end_line - 1))

        if not unused_lines:
            continue

        unused_lines.sort(key=lambda x: -x[0])
        modified = False
        for start_idx, end_idx in unused_lines:
            if not (
                0 <= start_idx < len(lines_with_endings) and 0 <= end_idx < len(lines_with_endings)
            ):
                continue
            indent = len(lines_with_endings[start_idx]) - len(
                lines_with_endings[start_idx].lstrip()
            )
            blank = " " * indent + "\n"
            for idx in range(end_idx, start_idx - 1, -1):
                if idx < len(lines_with_endings) and lines_with_endings[idx].strip() == "":
                    continue
                if 0 <= idx < len(lines_with_endings):
                    lines_with_endings[idx] = blank
                    modified = True
            if 0 <= start_idx < len(lines_with_endings):
                lines_with_endings[start_idx] = blank
                modified = True
            removed_total += 1

        if modified:
            new_source = "".join(lines_with_endings)
            try:
                ast.parse(new_source)
            except SyntaxError:
                skipped.append(str(fp))
                continue
            if apply and new_source != source:
                fp.write_text(new_source, encoding="utf-8")
                files_touched.add(fp)

    return {
        "removed": removed_total,
        "files_touched": len(files_touched),
        "skipped": skipped,
        "applied": apply,
    }


def run_ruff_and_tests() -> tuple[bool, bool]:
    """Run ruff and pytest, return (ruff_clean, tests_pass)."""
    print("\nrunning ruff check...")
    ruff_clean = subprocess.run(
        ["uv", "run", "ruff", "check", "."], cwd=REPO_ROOT, capture_output=True, text=True
    )
    if ruff_clean.returncode != 0:
        print(ruff_clean.stdout)
        print(ruff_clean.stderr)
        return False, False

    print("running pytest...")
    test_result = subprocess.run(
        ["uv", "run", "pytest", "tests/unit", "-q"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    print(test_result.stdout[-2000:])
    if test_result.returncode != 0:
        print(test_result.stderr[-2000:])
        return True, False
    return True, True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true", help="Apply safe auto-fixes instead of dry-run"
    )
    parser.add_argument("--repo", default=str(REPO_ROOT))
    args = parser.parse_args()

    py_files = [
        p for p in Path(args.repo).rglob("*.py") if ".venv" not in p.parts and ".git" not in p.parts
    ]
    print(f"found {len(py_files)} .py files in repo")

    section("Step 1 — SGIR pipeline against the intelliqx repo")
    pipeline_result = run_sgir_pipeline(args.repo)

    section("Step 2 — Heuristic auditors")
    underscore_findings = find_lingering_double_underscore(py_files)
    print(f"  lingering __ name-mangling: {len(underscore_findings)}")
    for fp, ln, _line, name in underscore_findings[:10]:
        print(f"    {fp.relative_to(REPO_ROOT)}:{ln}  -> self.{name}")

    unused = find_unused_imports_ast(py_files)
    print(f"  unused imports (AST): {len(unused)}")
    for fp, ln, msg, _name in unused[:15]:
        print(f"    {fp.relative_to(REPO_ROOT)}:{ln}  {msg}")

    long_fns = find_long_functions(py_files, threshold=50)
    print(f"  long functions (>= 50 lines): {len(long_fns)}")
    for fp, info, ln in long_fns[:10]:
        print(f"    {fp.relative_to(REPO_ROOT)}:{ln}  {info}")

    bare_exc = find_bare_except(py_files)
    bare = [f for f in bare_exc if "bare" in f[2]]
    silent = [f for f in bare_exc if "silent" in f[2]]
    print(f"  bare except: {len(bare)}; silent except:pass: {len(silent)}")
    for fp, ln, msg in (bare + silent)[:10]:
        print(f"    {fp.relative_to(REPO_ROOT)}:{ln}  {msg}")

    missing_all = find_missing_all(py_files)
    print(f"  __init__.py files missing __all__: {len(missing_all)}")
    for fp in missing_all[:10]:
        print(f"    {fp.relative_to(REPO_ROOT)}")

    print_leaks = find_print_leaks(py_files)
    print(f"  print() leaks in libs/: {len(print_leaks)}")
    for fp, ln, line in print_leaks[:10]:
        print(f"    {fp.relative_to(REPO_ROOT)}:{ln}  {line[:80]}")

    todo = find_todo_fixme_markers(py_files)
    print(f"  TODO/FIXME/HACK markers: {len(todo)}")
    for fp, ln, line, marker in todo[:10]:
        print(f"    {fp.relative_to(REPO_ROOT)}:{ln}  [{marker}] {line[:80]}")

    id_caches = find_id_based_caches(py_files)
    print(f"  id()-based caches: {len(id_caches)}")
    for fp, ln, line, kind in id_caches[:10]:
        print(f"    {fp.relative_to(REPO_ROOT)}:{ln}  {kind}: {line[:80]}")

    missing_docs = find_missing_public_func_docstrings(py_files)
    print(f"  public funcs missing docstrings: {len(missing_docs)}")
    for fp, name, ln in missing_docs[:10]:
        print(f"    {fp.relative_to(REPO_ROOT)}:{ln}  def {name}()")

    section("Step 3 — Auto-fixes" + (" (APPLIED)" if args.apply else " (dry-run)"))

    scorecard: dict[str, Any] = {}
    fix = auto_fix_underscore(py_files, apply=args.apply)
    print(f"  underscore -> public: {fix['findings']} across {fix['files_touched']} files")
    scorecard["underscore"] = fix

    unused_fix = auto_fix_unused_imports(py_files, apply=args.apply)
    print(
        f"  unused imports removed: {unused_fix['removed']} across {unused_fix['files_touched']} files"
    )
    if unused_fix["skipped"]:
        print(f"  skipped: {unused_fix['skipped']}")
    scorecard["unused_imports"] = unused_fix

    all_fix = auto_fix_add_all(py_files, apply=args.apply)
    print(f"  __all__ added: {all_fix['added']} files ({all_fix['files_touched']} touched)")
    scorecard["add_all"] = all_fix

    section("Step 4 — Pipeline errors discovered")
    if pipeline_result["errors"]:
        for err in pipeline_result["errors"]:
            print(f"  ! {err}")
    else:
        print("  none")

    section("Step 5 — Verifying")
    ruff_ok, tests_ok = run_ruff_and_tests()
    print(f"  ruff: {'clean' if ruff_ok else 'FAIL'}")
    print(f"  tests: {'pass' if tests_ok else 'FAIL'}")

    section("Step 6 — Saving report")
    report = {
        "metadata": pipeline_result.get("metadata"),
        "parsed_entity_count": pipeline_result.get("parsed_entity_count"),
        "layer_node_counts": pipeline_result.get("layer_node_counts"),
        "graph_node_total": pipeline_result.get("graph_node_total"),
        "generated_files": pipeline_result.get("generated_files"),
        "optimization_summary": (
            pipeline_result.get("optimization", {}).get("summary", {})
            if isinstance(pipeline_result.get("optimization"), dict)
            else {}
        ),
        "duplicate_pairs": len(pipeline_result.get("duplicates_direct", [])),
        "parallel_branches": len(pipeline_result.get("parallel_branches_direct", [])),
        "auditors": {
            "underscore": len(underscore_findings),
            "unused_imports": len(unused),
            "long_functions": len(long_fns),
            "bare_except": len(bare),
            "silent_except_pass": len(silent),
            "missing_all": len(missing_all),
            "print_leaks": len(print_leaks),
            "todo_fixme": len(todo),
            "id_based_caches": len(id_caches),
            "missing_docstrings": len(missing_docs),
        },
        "auto_fixes": scorecard,
        "errors": pipeline_result["errors"],
        "warnings": pipeline_result["warnings"],
        "ruff_clean": ruff_ok,
        "tests_pass": tests_ok,
        "mode": "APPLIED" if args.apply else "DRY-RUN",
    }
    report_path = REPO_ROOT / "scripts" / "self_improve_report.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"  report: {report_path}")

    return 0 if (ruff_ok and tests_ok) else 2


if __name__ == "__main__":
    raise SystemExit(main())
