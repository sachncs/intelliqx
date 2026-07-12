"""Code Intelligence Agent (Tier 2).

Analyzes a set of source files and produces an impact graph plus a
dependency graph. The agent is the bridge between the planner
(which decides *what* to run) and the execution layer (which
re-runs tests for *affected* files only).

Implementation notes:

* **Regex-based Python import extraction.** We deliberately avoid a
  real Python AST parser to keep the agent zero-dep. The extraction
  covers ``import x`` and ``from x import y`` for the top-level
  module path; deeper relative imports are folded into the same
  string. False positives are rare and don't affect downstream
  consumers (KG + RAG) which only use the dependency hints for
  traversal, not for execution.
* **Path-based dep resolution.** We map an extracted module
  symbol back to a file in the input set by suffix-matching
  (``endswith("foo.py")``). The best-effort match is what the
  planner uses to know "if ``src/a.py`` changed, also retest
  ``src/b.py`` because ``b`` imports ``a``".
"""

from __future__ import annotations

import re
from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.ids import new_id
from intelliqx_kg.graph import Edge, Node, get_kg
from pydantic import BaseModel, ConfigDict, Field

from agents.tier2.models import CodeImpactGraph


class CodeIntelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: list[dict[str, Any]]  # [{"path": ..., "content": ...}, ...]
    tenant_id: str
    changed_paths: list[str] = Field(default_factory=list)


class CodeIntelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph: CodeImpactGraph
    files_indexed: int = 0


class CodeIntelAgent(AgentBase):
    META = AgentMeta(
        name="code_intel",
        tier=2,
        version="0.1.0",
        description="Builds impact + dependency graphs from code.",
    )
    INPUT_MODEL = CodeIntelInput
    OUTPUT_MODEL = CodeIntelOutput

    @traced_agent("code_intel")
    async def run(self, ctx: AgentContext, input: CodeIntelInput) -> CodeIntelOutput:
        kg = get_kg()
        nodes: list[Node] = []
        edges: list[Edge] = []
        deps_per_file: dict[str, set[str]] = {}

        for f in input.files:
            path = f["path"]
            content = f.get("content", "")
            deps = _extract_imports(content)
            deps_per_file[path] = deps
            # Each file gets a fresh ``file-<ulid>`` node id so the
            # node identity is stable across runs of the same input.
            node_id = f"file-{new_id()}"
            nodes.append(
                Node(
                    id=node_id,
                    type="File",
                    tenant_id=input.tenant_id,
                    attrs={"path": path, "loc": len(content.splitlines())},
                )
            )

        if nodes:
            await kg.add_nodes(nodes)

        # Map deps back to file IDs by best-effort path matching.
        # We match on the last segment (``a.b.c`` → ``c``) to
        # support both ``from foo.bar import baz`` and the file
        # path ``src/baz.py``.
        path_to_id = {n.attrs["path"]: n.id for n in nodes}
        for src_path, deps in deps_per_file.items():
            src_id = path_to_id.get(src_path)
            if not src_id:
                continue
            for dep in deps:
                dep_basename = dep.split(".")[-1] if "." in dep else dep
                tgt = next(
                    (
                        pid
                        for p, pid in path_to_id.items()
                        if p.endswith(dep_basename + ".py") or p.endswith(dep_basename)
                    ),
                    None,
                )
                if tgt:
                    edges.append(
                        Edge(
                            src=src_id,
                            dst=tgt,
                            type="IMPORTS",
                            tenant_id=input.tenant_id,
                            attrs={"symbol": dep},
                        )
                    )
        if edges:
            await kg.add_edges(edges)

        # Determine impact: changed files + their transitive
        # dependents. If no changed_paths provided, we treat every
        # file as "changed" (useful for the initial baseline run).
        changed_set = set(input.changed_paths)
        affected = set(changed_set)
        for e in edges:
            for cp in changed_set:
                if e.dst in path_to_id and path_to_id[e.dst].endswith(cp.split("/")[-1]):
                    src_path = next((p for p, pid in path_to_id.items() if pid == e.src), None)
                    if src_path:
                        affected.add(src_path)
        if not changed_set:
            affected = {n.attrs["path"] for n in nodes}

        impact_summary = (
            f"Analyzed {len(nodes)} files; {len(edges)} import edges; "
            f"{len(affected)} files impacted by changes."
        )

        return CodeIntelOutput(
            graph=CodeImpactGraph(
                affected_files=sorted(affected),
                dependencies=[
                    {"from": e.src, "to": e.dst, "symbol": e.attrs.get("symbol")} for e in edges
                ],
                impact_summary=impact_summary,
            ),
            files_indexed=len(nodes),
        )


def _extract_imports(content: str) -> set[str]:
    """Extract Python top-level module names from ``content``.

    Covers the two most common forms:

    * ``import a.b.c``   → ``"a.b.c"``
    * ``from a.b.c import d`` → ``"a.b.c"``

    Returns:
        The set of unique top-level module strings.
    """
    deps: set[str] = set()
    for m in re.finditer(r"^\s*from\s+([\w.]+)\s+import", content, flags=re.MULTILINE):
        deps.add(m.group(1))
    for m in re.finditer(r"^\s*import\s+([\w.]+)", content, flags=re.MULTILINE):
        deps.add(m.group(1))
    return deps
