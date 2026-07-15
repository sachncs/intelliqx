"""Memory Manager Agent (Coordination).

Provides a unified memory API across working, episodic, semantic, and
code memories. The agent uses **polymorphic dispatch** on the
``operation`` field of the input payload — the same compute path
handles all five operations (Put, Get, Search, Summarize, Forget)
without requiring the caller to switch agent names.

Storage layout:

* **Working memory** — fast, TTL-bounded. Backed by
  :class:`intelliqx_state.store.StateStore` (Redis in production). Key
  shape: ``{tenant_id}:working:{key}``.
* **Episodic / semantic / code memory** — durable. Backed by
  :class:`intelliqx_storage.store.ObjectStore` (S3 / GCS / Modal Volume in
  production). Key shape: ``{tenant_id}/{memory_type}/{key}``.

The two key shapes look different on purpose: state-store keys are
flat (one big namespace) while object-store keys are
hierarchical (the prefix encodes the memory type).
"""

from __future__ import annotations

import time
from contextlib import suppress
from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory
from intelliqx_state.store import get_state_store
from intelliqx_storage.store import get_object_store
from pydantic import BaseModel, ConfigDict, Field


class MemoryManagerInput(BaseModel):
    """Write ``value`` under ``key`` in the given ``memory_type``."""

    model_config = ConfigDict(extra="forbid")

    key: str
    value: str
    memory_type: str = "working"  # working | episodic | semantic | code
    ttl_seconds: int | None = None


class MemoryGet(BaseModel):
    """Read the value at ``key`` in ``memory_type``.

    Attributes:
        key: Logical key within the memory namespace.
        memory_type: One of ``"working"``, ``"episodic"``, ``"semantic"``,
            ``"code"``. Determines the backing store.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    memory_type: str = "working"


class MemorySearch(BaseModel):
    """Keyword search over the values stored in ``memory_type``.

    Attributes:
        query: Free-form search string. Whitespace-split into
            case-insensitive terms; a document matches if **any** term
            appears in its body.
        memory_type: Memory namespace to search. Defaults to
            ``"semantic"`` (the most common use case).
        top_k: Maximum number of results to return. Sorted by term
            frequency, descending.
    """

    model_config = ConfigDict(extra="forbid")

    query: str
    memory_type: str = "semantic"
    top_k: int = 5


class MemorySummarize(BaseModel):
    """Compress a list of episodic entries into a single semantic entry.

    Attributes:
        keys: Episodic-memory keys to fold into the summary.
        target_key: Destination key in semantic memory where the
            summary is written.
    """

    model_config = ConfigDict(extra="forbid")

    keys: list[str]
    target_key: str


class MemoryForget(BaseModel):
    """Remove ``key`` from ``memory_type``.

    Idempotent: forgetting a missing key is a no-op.

    Attributes:
        key: Logical key within the memory namespace.
        memory_type: Memory namespace to forget from.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    memory_type: str = "working"


def infer_op(payload: dict) -> str:
    """Infer the operation from payload keys when ``operation`` isn't explicit.

    Heuristic priority (most specific first):
        1. ``summarize``  — needs ``keys`` + ``target_key``.
        2. ``search``     — needs ``query``.
        3. ``put``        — needs ``key``, ``value``, ``memory_type``.
        4. ``forget``     — needs ``key``, ``memory_type``, no value.
        5. ``get``        — needs ``key``, ``memory_type``.

    ``get`` is the catch-all because forgetting is rare; callers
    that need explicit forget should pass ``operation="forget"``.
    """
    keys = set(payload.keys())
    if "keys" in keys and "target_key" in keys:
        return "summarize"
    if "query" in keys:
        return "search"
    if "value" in keys and "key" in keys and "memory_type" in keys:
        return "put"
    if "key" in keys and "memory_type" in keys:
        return "forget" if "operation" in payload and payload["operation"] == "forget" else "get"
    return "get"


MODEL_BY_OP: dict[str, type[BaseModel]] = {
    "put": MemoryManagerInput,
    "get": MemoryGet,
    "search": MemorySearch,
    "summarize": MemorySummarize,
    "forget": MemoryForget,
}


class MemoryOutput(BaseModel):
    """The result of any memory operation.

    The shape varies by operation; the union of all possible fields
    is exposed here for simplicity.

    Attributes:
        operation: Which operation produced this result
            (``"put"``, ``"get"``, ``"search"``, ``"summarize"``,
            ``"forget"``, ``"unknown"``).
        success: ``False`` only for unrecoverable failures.
        value: Set for Get / Put / Summarize (the stored or computed
            payload).
        results: Set for Search — each entry has ``key``, ``score``,
            and ``preview``.
        error: Error message on failure; ``None`` on success.
    """

    model_config = ConfigDict(extra="forbid")

    operation: str
    success: bool = True
    value: str | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class MemoryManagerAgent(AgentBase):
    """Manages short/medium/long-term memory for the platform.

    See module docstring for the storage layout and the
    polymorphic-dispatch contract.
    """

    META = AgentMeta(
        name="memory_manager",
        category=AgentCategory.COORDINATION,
        version="0.1.0",
        description="Unified memory API: working, episodic, semantic, code memories.",
    )
    # INPUT_MODEL is declared as the most common operation (Put) so
    # the default :meth:`AgentBase.invoke` works for the simple
    # case. The custom :meth:`invoke` below handles the other four
    # by inferring the right input model from the ``operation``
    # field.
    INPUT_MODEL = MemoryManagerInput
    OUTPUT_MODEL = MemoryOutput

    async def invoke(self, request):
        """Polymorphic dispatch: pick the right input model from the operation.

        The compute runtime calls this with a generic request envelope;
        we inspect ``request.input`` to determine which of the five
        operation models to validate against, then delegate to
        :meth:`run`. This is intentionally not a static dispatch — the
        same agent registry key (``"memory_manager"``) handles every
        memory operation so callers don't need to know which
        sub-agent to invoke.

        Args:
            request: The invocation request envelope. ``request.input``
                must be a JSON-serialisable dict carrying the
                operation's fields. The optional ``operation`` key
                pins the operation explicitly; otherwise the
                operation is inferred from the payload shape.

        Returns:
            The serialised :class:`MemoryOutput`.
        """
        from intelliqx_agents.base import AgentContext
        from intelliqx_core.models import TenantContext

        payload = dict(request.input)
        op = payload.pop("operation", None) or infer_op(payload)
        model = MODEL_BY_OP.get(op, MemoryManagerInput)
        inp = model.model_validate(payload)
        ctx = AgentContext(
            tenant=TenantContext(
                tenant_id=request.tenant_id, trace_id=request.metadata.get("trace_id")
            ),
            run_id=request.metadata.get("run_id", "unknown"),
        )
        out = await self.run(ctx, inp)
        return out.model_dump(mode="json")

    @traced_agent("memory_manager")
    async def run(self, ctx: AgentContext, input: MemoryManagerInput) -> MemoryOutput:
        # ``input`` is typed as MemoryManagerInput (the most common case)
        # but the actual instance may be any of the five operation
        # models — we branch on isinstance.
        tenant_id = ctx.tenant.tenant_id
        if isinstance(input, MemoryManagerInput):
            return await self.put(tenant_id, input)
        if isinstance(input, MemoryGet):
            return await self.get(tenant_id, input)
        if isinstance(input, MemorySearch):
            return await self.search(tenant_id, input)
        if isinstance(input, MemorySummarize):
            return await self.summarize(tenant_id, input)
        if isinstance(input, MemoryForget):
            return await self.forget(tenant_id, input)
        return MemoryOutput(operation="unknown", success=False, error="Unknown op")

    async def put(self, tenant_id: str, op: MemoryManagerInput) -> MemoryOutput:
        """Store ``op.value`` under ``op.key`` in ``op.memory_type``."""
        state = get_state_store()
        store = get_object_store()
        key = f"{tenant_id}:{op.memory_type}:{op.key}"
        if op.memory_type == "working":
            # Working memory lives in the state store with a
            # default 1h TTL if the caller didn't specify one.
            await state.set(key, op.value.encode("utf-8"), ttl_seconds=op.ttl_seconds or 3600)
        else:
            await store.put(
                f"{tenant_id}/{op.memory_type}/{op.key}",
                op.value.encode("utf-8"),
                content_type="text/plain",
            )
        return MemoryOutput(operation="put", success=True)

    async def get(self, tenant_id: str, op: MemoryGet) -> MemoryOutput:
        """Read the value at ``op.key`` in ``op.memory_type``."""
        state = get_state_store()
        store = get_object_store()
        key = f"{tenant_id}:{op.memory_type}:{op.key}"
        if op.memory_type == "working":
            data = await state.get(key)
        else:
            try:
                data = await store.get(f"{tenant_id}/{op.memory_type}/{op.key}")
            except Exception:
                data = None
        return MemoryOutput(
            operation="get", success=True, value=data.decode("utf-8") if data else None
        )

    async def search(self, tenant_id: str, op: MemorySearch) -> MemoryOutput:
        """Keyword search over the values in ``op.memory_type``.

        Algorithm: linear scan over the object-store listing,
        term-frequency scoring (whitespace-split query, case-
        insensitive), top-k by score.
        """
        store = get_object_store()
        prefix = f"{tenant_id}/{op.memory_type}/"
        results: list[dict[str, Any]] = []
        terms = [t.lower() for t in op.query.split() if t]
        async for key in store.list(prefix):
            try:
                blob = await store.get(key)
            except Exception:
                continue
            text = blob.decode("utf-8", errors="ignore")
            # Empty term list matches every document; this lets
            # callers do ``search(query="")`` to list the prefix.
            if not terms or any(t in text.lower() for t in terms):
                results.append(
                    {
                        "key": key,
                        "score": sum(text.lower().count(t) for t in terms),
                        "preview": text[:120],
                    }
                )
        results.sort(key=lambda r: -r["score"])
        return MemoryOutput(operation="search", success=True, results=results[: op.top_k])

    async def summarize(self, tenant_id: str, op: MemorySummarize) -> MemoryOutput:
        """Build a single summary string from the listed episodic entries.

        The summary is a simple concatenation of the first 200
        characters of each source value, joined with ``|`` and
        prefixed with a timestamp. Production deployments should
        swap this for an LLM call.
        """
        state = get_state_store()
        store = get_object_store()
        snippets: list[str] = []
        for k in op.keys:
            try:
                blob = await store.get(f"{tenant_id}/episodic/{k}")
                snippets.append(blob.decode("utf-8", errors="ignore")[:200])
            except Exception:
                # Silent pass is intentional: a missing episodic entry
                # (e.g. already forgotten, or a stale key in the
                # summarize request) should not abort the entire
                # summarization.  We skip it and continue with the
                # remaining entries.  The caller can detect partial
                # results by checking whether ``snippets`` is empty.
                pass
        if not snippets:
            data = b""
        else:
            data = ("SUMMARY(" + str(time.time()) + "): " + " | ".join(snippets)).encode("utf-8")
        await store.put(f"{tenant_id}/semantic/{op.target_key}", data, content_type="text/plain")
        # Invalidate any stale working-memory cache copy.
        await state.delete(f"{tenant_id}:semantic:{op.target_key}")
        return MemoryOutput(
            operation="summarize", success=True, value=data.decode("utf-8") if data else None
        )

    async def forget(self, tenant_id: str, op: MemoryForget) -> MemoryOutput:
        """Remove ``op.key`` from ``op.memory_type``.

        The object-store delete is wrapped in ``suppress`` so a
        missing key doesn't fail the operation.
        """
        state = get_state_store()
        store = get_object_store()
        await state.delete(f"{tenant_id}:{op.memory_type}:{op.key}")
        with suppress(Exception):
            await store.delete(f"{tenant_id}/{op.memory_type}/{op.key}")
        return MemoryOutput(operation="forget", success=True)
