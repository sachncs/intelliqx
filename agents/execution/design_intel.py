"""Design Intelligence Agent (Execution).

Extracts a semantic UI model from a DOM snapshot. The agent:

1. **Parses the HTML** to find interactive elements
   (``button``, ``input``, ``a``, ``form``, ``nav``, ``section``,
   etc.) and their ids, aria-labels, and visible text.
2. **Infers a workflow** from the elements (presence of a form
   plus a submit button implies "fill form, click submit", etc.).
3. **Persists each element as a KG node** so downstream agents
   (RAG, accessibility) can traverse the page structure.

The HTML parser is **regex-based**, not a real HTML parser. We
deliberately avoid BeautifulSoup / lxml to keep the agent
zero-dep. The trade-off is that the parser handles a fixed
set of tag patterns and may miss exotic or malformed HTML — fine
for tests and the reference app; production should use a real
parser.
"""

from __future__ import annotations

import re
from typing import ClassVar

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory
from intelliqx_kg.graph import Node, get_kg
from pydantic import BaseModel, ConfigDict, Field


class DesignIntelInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dom_html: str
    base_url: str
    tenant_id: str


class UIElement(BaseModel):
    """A single parsed UI element.

    Attributes:
        id: The HTML ``id`` attribute (or ``None`` if the tag has
            no id).
        tag: Lowercase HTML tag name.
        label: Value of the ``aria-label`` attribute (or ``None``).
        role: Lowercase tag name, used as a coarse ARIA role
            fallback.
        text: Visible text content (inner HTML stripped of tags,
            truncated to 80 chars) for tags that wrap text.
        selector: Preferred CSS selector for the element —
            ``"#{id}"`` when an id is present, otherwise the bare
            tag name.
        children: Reserved for future parent/child relationships;
            always empty in v1.
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    tag: str
    label: str | None = None
    role: str | None = None
    text: str | None = None
    selector: str
    children: list[str] = Field(default_factory=list)


class DesignIntelOutput(BaseModel):
    """Output payload for the Design Intelligence agent.

    Attributes:
        elements: Every parsed UI element on the page.
        workflow_steps: High-level workflow inferred from the
            elements (see :func:`_infer_workflow`).
        semantic_graph_id: Reserved for future KG graph-id
            population; always ``None`` in v1.
    """

    model_config = ConfigDict(extra="forbid")

    elements: list[UIElement] = Field(default_factory=list)
    workflow_steps: list[str] = Field(default_factory=list)
    semantic_graph_id: str | None = None


class DesignIntelAgent(AgentBase):
    META = AgentMeta(
        name="design_intel",
        category=AgentCategory.EXECUTION,
        version="0.1.0",
        description="Extracts semantic UI graph from DOM snapshots.",
    )
    INPUT_MODEL = DesignIntelInput
    OUTPUT_MODEL = DesignIntelOutput

    # Tags we care about for interactive UI. Anything outside this
    # set is ignored; the parser deliberately avoids generic
    # span/div noise.
    INTERACTIVE_TAGS: ClassVar[str] = (
        "button|input|a|form|nav|section|header|main|h1|h2|ul|li|select|textarea|label"
    )

    @traced_agent("design_intel")
    async def run(self, ctx: AgentContext, input: DesignIntelInput) -> DesignIntelOutput:
        elements = _parse_dom(input.dom_html, interactive_tags=self.INTERACTIVE_TAGS)
        workflow = _infer_workflow(elements)
        # Persist to KG so other agents (RAG, accessibility) can
        # query the page structure. The selector is the node id
        # because selectors are stable identifiers within a page.
        kg = get_kg()
        nodes: list[Node] = []
        for el in elements:
            nodes.append(
                Node(
                    id=el.selector,
                    type="UIElement",
                    tenant_id=input.tenant_id,
                    attrs={"tag": el.tag, "label": el.label, "role": el.role, "text": el.text},
                )
            )
        if nodes:
            await kg.add_nodes(nodes)
        return DesignIntelOutput(elements=elements, workflow_steps=workflow)


def _parse_dom(html: str, *, interactive_tags: str | None = None) -> list[UIElement]:
    """Extract interactive UI elements from ``html``.

    ``interactive_tags`` defaults to the agent's
    :attr:`DesignIntelAgent.INTERACTIVE_TAGS` regex. Tests that
    want a different tag set can pass their own regex.

    We use a two-step approach:

    1. Find every opening tag for an interactive element. This
       works even when the corresponding closing tag is missing
       (the regex is non-greedy by virtue of matching opening
       tags only, not whole elements).
    2. For tags that typically contain visible text, walk the
       HTML forward to the matching closing tag and extract the
       inner text with the tags stripped.

    Returns:
        A list of :class:`UIElement` records.
    """
    out: list[UIElement] = []
    if interactive_tags is None:
        interactive_tags = DesignIntelAgent.INTERACTIVE_TAGS
    tag_pat = re.compile(rf"<({interactive_tags})\b([^>]*)>", re.IGNORECASE)
    for m in tag_pat.finditer(html):
        tag = m.group(1).lower()
        attrs = m.group(2) or ""
        id_m = re.search(r'id="([^"]+)"', attrs)
        aria_m = re.search(r'aria-label="([^"]+)"', attrs)
        text: str | None = None
        # Tags that wrap visible text: extract the inner content.
        if tag in ("button", "a", "h1", "h2", "label", "li"):
            close_pat = re.compile(rf"</{tag}\s*>", re.IGNORECASE)
            close = close_pat.search(html, m.end())
            if close:
                # Strip nested tags from the inner text.
                inner = html[m.end() : close.start()].strip()
                text = re.sub(r"<[^>]+>", "", inner)[:80] or None
        selector = f"#{id_m.group(1)}" if id_m else tag
        out.append(
            UIElement(
                id=id_m.group(1) if id_m else None,
                tag=tag,
                label=aria_m.group(1) if aria_m else None,
                role=tag,
                text=text,
                selector=selector,
            )
        )
    return out


def _infer_workflow(elements: list[UIElement]) -> list[str]:
    """Infer high-level user workflow steps from the parsed elements.

    Heuristic:

    * Form + submit button → "Fill form fields" then "Click submit".
    * Any ``<a>`` element → "Navigate via links".
    """
    steps: list[str] = []
    has_form = any(e.tag == "form" for e in elements)
    has_button = any(e.tag == "button" for e in elements)
    has_link = any(e.tag == "a" for e in elements)
    if has_form:
        steps.append("Fill form fields")
        if has_button:
            steps.append("Click submit button")
    if has_link:
        steps.append("Navigate via links")
    return steps
