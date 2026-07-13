"""Prompt Management Agent (Tier 2).

Maintains versioned prompts, runs A/B tests, and bandit-routes
requests to the best-performing version. The agent has four
actions:

* ``list`` — return every registered prompt for the tenant.
* ``register`` — add a new prompt version.
* ``ab_record`` — record an outcome (``"passed"`` or ``"failed"``)
  for a (prompt, version) pair.
* ``select`` — return the prompt version with the highest
  Thompson-sampled success probability.

Bandit algorithm: Thompson sampling with a ``Beta(1+p, 1+n-p)``
prior where ``p`` is the number of passes and ``n`` is the total
number of trials. Each call samples a value from each version's
posterior and returns the argmax. This balances exploration and
exploitation: a poorly-performing version can recover when a few
passes arrive, and a well-performing version dominates after
enough samples.
"""

from __future__ import annotations

import json
import random

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_state.store import get_state_store
from pydantic import BaseModel, ConfigDict, Field


class PromptVersion(BaseModel):
    """A single prompt version.

    ``metrics`` carries aggregated pass/fail counts for
    display; the canonical values live in the state store under
    the ``ab:*`` keys.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_id: str
    version: str
    text: str
    metrics: dict[str, float] = Field(default_factory=dict)


class PromptMgmtInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: str  # list | register | ab_record | select
    tenant_id: str
    prompt_id: str | None = None
    version: str | None = None
    text: str | None = None
    outcome: str | None = None  # for ab_record: passed | failed


class PromptMgmtOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompts: list[PromptVersion] = Field(default_factory=list)
    selected: PromptVersion | None = None


class PromptManagementAgent(AgentBase):
    META = AgentMeta(
        name="prompt_management",
        tier=2,
        version="0.1.0",
        description="Manages prompt versions and A/B tests.",
    )
    INPUT_MODEL = PromptMgmtInput
    OUTPUT_MODEL = PromptMgmtOutput

    @traced_agent("prompt_management")
    async def run(self, ctx: AgentContext, input: PromptMgmtInput) -> PromptMgmtOutput:
        state = get_state_store()
        if input.action == "list":
            return PromptMgmtOutput(prompts=await _list_prompts(state, input.tenant_id))
        if input.action == "register":
            pv = PromptVersion(
                prompt_id=input.prompt_id or "",
                version=input.version or "v1",
                text=input.text or "",
            )
            await state.set(
                f"prompt:{input.tenant_id}:{pv.prompt_id}:{pv.version}",
                pv.model_dump_json().encode("utf-8"),
            )
            return PromptMgmtOutput(prompts=[pv])
        if input.action == "ab_record":
            # Track outcome per (prompt_id, version). The first
            # state-store key is the total trial count; the second
            # is the pass count. Both are stored as decimal strings
            # to keep the wire format consistent with the
            # bandit-select path.
            ab_key = f"ab:{input.tenant_id}:{input.prompt_id}:{input.version}"
            cur = await state.get(ab_key)
            n = int(cur.decode()) if cur else 0
            await state.set(ab_key, str(n + 1).encode("utf-8"))
            pass_key = f"ab_pass:{input.tenant_id}:{input.prompt_id}:{input.version}"
            if input.outcome == "passed":
                cur = await state.get(pass_key)
                n = int(cur.decode()) if cur else 0
                await state.set(pass_key, str(n + 1).encode("utf-8"))
            return PromptMgmtOutput()
        if input.action == "select":
            return PromptMgmtOutput(
                selected=await _bandit_select(state, input.tenant_id, input.prompt_id or "")
            )
        return PromptMgmtOutput()


async def _list_prompts(state, tenant_id: str) -> list[PromptVersion]:
    """Return every registered prompt version for the tenant."""
    out: list[PromptVersion] = []
    async for k in state.keys(f"prompt:{tenant_id}:"):
        blob = await state.get(k)
        if not blob:
            continue
        try:
            out.append(PromptVersion.model_validate(json.loads(blob.decode())))
        except Exception:
            # Skip malformed entries.
            continue
    return out


async def _bandit_select(state, tenant_id: str, prompt_id: str) -> PromptVersion | None:
    """Pick the highest-Thompson-sampled prompt version.

    For each version we draw ``Beta(1+p, 1+n-p)`` where ``p`` is
    the number of passes and ``n`` is the total trials. A version
    with no data still gets a draw from ``Beta(1, 1)`` (the uniform
    distribution), so it has a non-zero chance of being selected
    initially.
    """
    versions: list[PromptVersion] = []
    async for k in state.keys(f"prompt:{tenant_id}:{prompt_id}:"):
        blob = await state.get(k)
        if not blob:
            continue
        try:
            versions.append(PromptVersion.model_validate(json.loads(blob.decode())))
        except Exception:
            continue
    if not versions:
        return None

    scored: list[tuple[float, PromptVersion]] = []
    for v in versions:
        ab_key = f"ab:{tenant_id}:{prompt_id}:{v.version}"
        ab_pass_key = f"ab_pass:{tenant_id}:{prompt_id}:{v.version}"
        n_blob = await state.get(ab_key)
        p_blob = await state.get(ab_pass_key)
        n = int(n_blob.decode()) if n_blob else 0
        p = int(p_blob.decode()) if p_blob else 0
        # ``a = 1+p`` and ``b = 1+(n-p)`` give us the conjugate
        # posterior for a Bernoulli likelihood.
        a = 1 + p
        b = 1 + max(0, n - p)
        score = random.betavariate(a, b)
        scored.append((score, v))
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]
