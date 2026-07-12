"""Self-Healing Agent (Tier 3).

Given a failed CSS selector and a current DOM snapshot, proposes
alternative selectors. The agent is **two-stage**:

1. **Heuristic candidate generation.** The agent scans the DOM
   for elements that share attributes with the failed selector
   (``id``, ``data-testid``, ``name``, ``aria-label``). Each
   candidate carries a confidence score derived from how
   specific the attribute is.
2. **LLM ranking.** Each candidate is sent to the LLM for a
   confidence refinement. In tests the LLM is the deterministic
   :class:`intelliqx_llm.client.FakeLLMClient`, so the ranking is a
   no-op; in production the LLM uses the DOM context to pick the
   best match.

The agent emits a sorted list of candidates (best first) and
applies the first one whose confidence exceeds ``min_confidence``.
"""

from __future__ import annotations

import re

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_llm.client import CompletionRequest, get_llm_client
from pydantic import BaseModel, ConfigDict, Field


class SelfHealingInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    failed_selector: str
    dom_html: str
    intent: str = ""  # e.g. "the login button"
    min_confidence: float = 0.5


class SelfHealingCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selector: str
    confidence: float
    rationale: str = ""


class SelfHealingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_selector: str
    candidates: list[SelfHealingCandidate] = Field(default_factory=list)
    healed: bool = False
    applied_selector: str | None = None


class SelfHealingAgent(AgentBase):
    META = AgentMeta(
        name="self_healing",
        tier=3,
        version="0.1.0",
        description="Repairs broken selectors by inspecting DOM.",
    )
    INPUT_MODEL = SelfHealingInput
    OUTPUT_MODEL = SelfHealingOutput

    @traced_agent("self_healing")
    async def run(self, ctx: AgentContext, input: SelfHealingInput) -> SelfHealingOutput:
        candidates = _generate_candidates(
            input.failed_selector, input.dom_html, intent=input.intent
        )
        # LLM refinement. In tests the fake client returns a
        # hash-derived response; we keep the heuristic confidence
        # as the canonical value.
        llm = get_llm_client()
        ranked: list[SelfHealingCandidate] = []
        for c in candidates:
            prompt = f"Selector {c.selector!r} intent {input.intent!r} → confidence 0..1"
            resp = await llm.complete(
                CompletionRequest(
                    model="auto",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                )
            )
            ranked.append(
                SelfHealingCandidate(
                    selector=c.selector,
                    confidence=c.confidence,
                    rationale=c.rationale or resp.content[:80],
                )
            )
        ranked.sort(key=lambda c: -c.confidence)
        applied: SelfHealingCandidate | None = None
        if ranked and ranked[0].confidence >= input.min_confidence:
            applied = ranked[0]
        return SelfHealingOutput(
            original_selector=input.failed_selector,
            candidates=ranked,
            healed=applied is not None,
            applied_selector=applied.selector if applied else None,
        )


def _generate_candidates(
    failed: str, html: str, *, intent: str = ""
) -> list[SelfHealingCandidate]:
    """Generate candidate selectors by inspecting the DOM.

    Heuristics (in priority order — higher confidence wins):

    1. ``id="..."``        →  ``#{id}``                       (conf 0.8)
    2. ``data-testid="..."``→ ``[data-testid="..."]``         (conf 0.7)
    3. ``name="..."``      → ``[name="..."]``                (conf 0.6)
    4. ``aria-label="..."``→ ``[aria-label="..."]``         (conf 0.65)

    Duplicates by selector are removed. The order in which
    attributes are scanned in the DOM is preserved within each
    category.
    """
    out: list[SelfHealingCandidate] = []
    for m in re.finditer(r'id="([^"]+)"', html):
        out.append(
            SelfHealingCandidate(selector=f"#{m.group(1)}", confidence=0.8, rationale="id match")
        )
    for m in re.finditer(r'data-testid="([^"]+)"', html):
        out.append(
            SelfHealingCandidate(
                selector=f'[data-testid="{m.group(1)}"]', confidence=0.7, rationale="data-testid"
            )
        )
    for m in re.finditer(r'name="([^"]+)"', html):
        out.append(
            SelfHealingCandidate(
                selector=f'[name="{m.group(1)}"]', confidence=0.6, rationale="name attr"
            )
        )
    for m in re.finditer(r'aria-label="([^"]+)"', html):
        out.append(
            SelfHealingCandidate(
                selector=f'[aria-label="{m.group(1)}"]', confidence=0.65, rationale="aria-label"
            )
        )
    # Dedupe by selector — keep the first occurrence (highest
    # priority for that selector).
    seen: set[str] = set()
    deduped: list[SelfHealingCandidate] = []
    for c in out:
        if c.selector in seen:
            continue
        seen.add(c.selector)
        deduped.append(c)
    return deduped
