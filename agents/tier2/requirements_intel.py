"""Requirements Intelligence Agent (Tier 2).

Parses a PRD (or any structured text) into a list of requirements
plus a traceability matrix. The agent is **deterministic and
dependency-free** in v1: it uses regex-based extraction that handles
the two most common PRD shapes:

* Numbered: ``"1. The system shall ..."``
* Bulleted: ``"- Search by keyword"``

Requirements priority is read from inline ``[high]`` / ``(critical)``
markers; otherwise ``"medium"`` is assumed. Acceptance criteria are
extracted from ``"AC: ..."`` or ``"Acceptance: ..."`` suffixes.

The agent persists nodes and edges to the
:class:`~intelliqx_kg.graph.KnowledgeGraph` so subsequent agents (RAG,
coverage analysis) can query the requirements without re-parsing
the source text.
"""

from __future__ import annotations

import re
from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.ids import new_id
from intelliqx_kg.graph import Edge, Node, get_kg
from pydantic import BaseModel, ConfigDict

from agents.tier2.models import RequirementsGraph


class RequirementsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    tenant_id: str
    source: str = "prd"


class RequirementsIntelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph: RequirementsGraph
    requirement_count: int = 0


class RequirementsIntelAgent(AgentBase):
    META = AgentMeta(
        name="requirements_intel",
        tier=2,
        version="0.1.0",
        description="Parses a PRD into structured requirements + traceability matrix.",
    )
    INPUT_MODEL = RequirementsInput
    OUTPUT_MODEL = RequirementsIntelOutput

    @traced_agent("requirements_intel")
    async def run(self, ctx: AgentContext, input: RequirementsInput) -> RequirementsIntelOutput:
        requirements = _extract_requirements(input.text)
        # Persist to KG
        kg = get_kg()
        nodes: list[Node] = []
        for r in requirements:
            # Each requirement gets a fresh ``req-<ulid>`` id so the
            # node id is stable even if the input text changes.
            rid = f"req-{new_id()}"
            nodes.append(
                Node(
                    id=rid,
                    type="Requirement",
                    tenant_id=input.tenant_id,
                    attrs={
                        "title": r["title"],
                        "priority": r["priority"],
                        "acceptance_criteria": r["acceptance_criteria"],
                    },
                )
            )
        # Build traceability edges between requirements that
        # share significant vocabulary. We add an edge for every
        # pair of requirements with at least one shared keyword.
        edges: list[Edge] = []
        for i, src in enumerate(nodes):
            for dst in nodes[i + 1 :]:
                shared = _shared_keywords(src.attrs.get("title", ""), dst.attrs.get("title", ""))
                if shared:
                    edges.append(
                        Edge(
                            src=src.id,
                            dst=dst.id,
                            type="RELATED_TO",
                            tenant_id=input.tenant_id,
                            attrs={"shared_keywords": shared},
                        )
                    )
        if nodes:
            await kg.add_nodes(nodes)
        if edges:
            await kg.add_edges(edges)

        graph = RequirementsGraph(
            requirements=[n.attrs | {"id": n.id} for n in nodes],
            traceability=[
                {"from": e.src, "to": e.dst, "shared_keywords": e.attrs.get("shared_keywords", [])}
                for e in edges
            ],
        )
        return RequirementsIntelOutput(graph=graph, requirement_count=len(nodes))


def _extract_requirements(text: str) -> list[dict[str, Any]]:
    """Extract requirements from a structured-text PRD.

    A "requirement" is any line that begins with a numbered
    (1./2./3.) or bulleted (-/*/•) marker. Lines that don't match
    the patterns are ignored.
    """
    out: list[dict[str, Any]] = []
    pat = re.compile(r"^(?:[-*•]|\d+[.)])\s+(.*)")
    for line in text.splitlines():
        m = pat.match(line.strip())
        if not m:
            continue
        content = m.group(1).strip()
        # Priority is taken from inline markers. We default to
        # "medium" when no marker is present so downstream code
        # always has a value to branch on.
        priority = "medium"
        for p in ("critical", "high", "medium", "low"):
            if f"[{p}]" in content.lower() or f"({p})" in content.lower():
                priority = p
                break
        # Acceptance criteria: optional ``"AC: ..."`` suffix on
        # the same line. We keep at most one criterion per line.
        ac: list[str] = []
        ac_match = re.search(r"(?:AC|Acceptance)[:\s]+(.*?)(?:\.\s|$)", content)
        if ac_match:
            ac = [ac_match.group(1).strip()]
        out.append(
            {
                "title": content,
                "priority": priority,
                "acceptance_criteria": ac,
            }
        )
    return out


def _shared_keywords(a: str, b: str) -> list[str]:
    """Return sorted shared content-words between two strings.

    Stopwords (``the``, ``a``, ``of`` …) and words of length <= 2
    are excluded. The result is sorted for stable test output.
    """
    stop = {"the", "a", "an", "and", "or", "of", "to", "be", "is", "are", "for", "in", "on"}
    ta = {w.lower() for w in re.findall(r"\w+", a) if w.lower() not in stop and len(w) > 2}
    tb = {w.lower() for w in re.findall(r"\w+", b) if w.lower() not in stop and len(w) > 2}
    return sorted(ta & tb)
