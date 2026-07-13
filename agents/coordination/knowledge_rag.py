"""Knowledge / RAG Agent (Coordination).

Four-source hybrid retriever:

1. **Vector** — embed the query and search the sqlite-vec
   index. The default backend is the embedded
   :class:`intelliqx_vector.SqliteVecIndex` (zvec is the
   alternate).
2. **KG** — find knowledge-graph nodes whose attributes contain
   the query tokens (SQL ``LIKE``).
3. **Lexical** — scan the tenant's episodic memory in the object
   store and rank by term frequency.
4. **OKF catalog** — query the
   :class:`intelliqx_okf.catalog.OKFCatalog` for structured
   metadata (``type``, ``tags``) and full-text relevance. The
   catalog also re-ranks using sqlite-vec embeddings when both
   the catalog and the agent's query embedding are available.

Sources 1-3 are combined via weighted reciprocal-rank fusion
(RRF, ``k=60``). Source 4 returns its own ranked list which is
fused alongside the others. The final ranking deduplicates by
document id (keeping the highest RRF score) and truncates to
``top_k``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory
from intelliqx_kg.graph import get_kg
from intelliqx_llm.client import get_llm_client
from intelliqx_okf.catalog import get_catalog
from intelliqx_storage.store import get_object_store
from intelliqx_vector.index import VectorDoc, get_vector_index
from pydantic import BaseModel, ConfigDict, Field

_RRF_K = 60


class KnowledgeRAGInput(BaseModel):
    """A RAG query.

    Attributes:
        query: The natural-language query.
        tenant_id: The owning tenant.
        top_k: Maximum number of documents to return.
        type_filter: Optional list of OKF ``type`` values to
            restrict the catalog leg (e.g. ``["API Endpoint"]``).
        tag_filter: Optional list of tags to require (all must be
            present).
        namespaces: Reserved for future use; the current
            implementation searches all sources.
    """

    model_config = ConfigDict(extra="forbid")

    query: str
    tenant_id: str
    top_k: int = 5
    type_filter: list[str] = Field(default_factory=list)
    tag_filter: list[str] = Field(default_factory=list)
    namespaces: list[str] = Field(default_factory=lambda: ["docs", "code", "episodic"])


class KnowledgeRAGDocument(BaseModel):
    """A single retrieval hit.

    ``source`` is one of ``"vector"``, ``"kg"``, ``"lexical"``,
    or ``"okf"``.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    score: float
    source: str  # vector | kg | lexical | okf


class KnowledgeRAGOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    documents: list[KnowledgeRAGDocument] = Field(default_factory=list)


class KnowledgeRAGAgent(AgentBase):
    """Four-source hybrid retriever.

    See module docstring for the full pipeline. Sources 1-3
    (``vector``, ``kg``, ``lexical``) are the original three;
    source 4 (``okf``) is the OKF catalog search.

    All four sources are fused via weighted reciprocal-rank fusion
    (RRF).  Each source has a configurable weight; the default
    weights emphasise vector and OKF retrieval.
    """

    META = AgentMeta(
        name="knowledge_rag",
        category=AgentCategory.COORDINATION,
        version="0.3.0",
        description="Hybrid retriever: vector + KG + lexical + OKF catalog (RRF).",
    )
    INPUT_MODEL = KnowledgeRAGInput
    OUTPUT_MODEL = KnowledgeRAGOutput

    # Source weights for RRF.  Higher weight = more influence.
    SOURCE_WEIGHTS: ClassVar[dict[str, float]] = {
        "vector": 1.0,
        "kg": 0.5,
        "lexical": 0.3,
        "okf": 1.2,
    }

    @traced_agent("knowledge_rag")
    async def run(self, ctx: AgentContext, input: KnowledgeRAGInput) -> KnowledgeRAGOutput:
        tenant_id = ctx.tenant.tenant_id
        llm = get_llm_client()
        vec_index = get_vector_index()
        kg = get_kg()
        store = get_object_store()
        catalog = get_catalog()

        query_vec = (await llm.embed([input.query], model="auto"))[0]

        # Collect per-source ordered candidate lists.
        source_lists: dict[str, list[KnowledgeRAGDocument]] = {
            "vector": [],
            "kg": [],
            "lexical": [],
            "okf": [],
        }

        # 1) Vector search
        vec_results = await vec_index.search(query_vec, top_k=input.top_k * 3, tenant_id=tenant_id)
        for r in vec_results:
            source_lists["vector"].append(
                KnowledgeRAGDocument(id=r.id, text=r.text or "", score=r.score, source="vector")
            )

        # 2) KG neighbors
        kg_rows = kg.query(
            "SELECT id, type, attrs FROM kg_nodes WHERE tenant_id = ? AND lower(attrs) LIKE ?",
            params=[tenant_id, f"%{input.query.lower()}%"],
        )
        for row in kg_rows.rows[: input.top_k * 3]:
            text = str(row.get("attrs", ""))
            source_lists["kg"].append(
                KnowledgeRAGDocument(id=str(row["id"]), text=text, score=0.5, source="kg")
            )

        # 3) Lexical — search episodic memory
        terms = [t.lower() for t in input.query.split() if t]
        scored: list[KnowledgeRAGDocument] = []
        async for key in store.list(f"{tenant_id}/episodic/"):
            try:
                blob = await store.get(key)
            except Exception:
                continue
            text = blob.decode("utf-8", errors="ignore")
            hits = sum(text.lower().count(t) for t in terms)
            if hits > 0:
                scored.append(
                    KnowledgeRAGDocument(
                        id=key, text=text[:400], score=float(hits), source="lexical"
                    )
                )
        scored.sort(key=lambda r: -r.score)
        source_lists["lexical"] = scored[: input.top_k * 3]

        # 4) OKF catalog
        catalog_hits = catalog.search(
            input.query,
            type_filter=input.type_filter or None,
            tag_filter=input.tag_filter or None,
            tenant_id=tenant_id,
            top_k=input.top_k * 3,
            query_embedding=query_vec,
            vector_weight=0.5,
        )
        for h in catalog_hits:
            source_lists["okf"].append(
                KnowledgeRAGDocument(
                    id=h.concept_id,
                    text=h.snippet or (h.description or h.title or ""),
                    score=h.score,
                    source="okf",
                )
            )

        # Weighted reciprocal-rank fusion.
        merged: dict[str, dict[str, Any]] = {}
        for source, candidates in source_lists.items():
            weight = self.SOURCE_WEIGHTS.get(source, 0.5)
            for rank, doc in enumerate(candidates):
                if doc.id not in merged:
                    merged[doc.id] = {"doc": doc, "rrf": 0.0}
                merged[doc.id]["rrf"] += weight / (_RRF_K + rank + 1)

        fused = sorted(merged.values(), key=lambda x: x["rrf"], reverse=True)[: input.top_k]
        docs = [
            KnowledgeRAGDocument(
                id=item["doc"].id,
                text=item["doc"].text,
                score=item["rrf"],
                source=item["doc"].source,
            )
            for item in fused
        ]
        return KnowledgeRAGOutput(query=input.query, documents=docs)

    async def ingest(
        self, *, tenant_id: str, doc_id: str, text: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Embed and upsert a document into the vector store.

        Args:
            tenant_id: Owning tenant.
            doc_id: Vector id (typically the document id).
            text: The text to embed.
            metadata: Optional metadata stored alongside the vector.
        """
        llm = get_llm_client()
        vec = (await llm.embed([text], model="auto"))[0]
        idx = get_vector_index()
        await idx.upsert(
            [
                VectorDoc(
                    id=doc_id, tenant_id=tenant_id, text=text, vector=vec, metadata=metadata or {}
                )
            ]
        )

    async def ingest_okf_concept(
        self,
        concept_id: str,
        text: str,
        *,
        tenant_id: str = "_global",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Embed ``text`` and store it in both the OKF catalog and the vector index.

        The OKF catalog holds the typed metadata; the vector index
        holds the embedding keyed by the same concept id. Both
        must be populated for hybrid retrieval to find the concept.
        """
        llm = get_llm_client()
        vec = (await llm.embed([text], model="auto"))[0]
        get_catalog().store_embedding(concept_id, vec, tenant_id=tenant_id)
        vec_id = f"okf::{tenant_id}::{concept_id}"
        idx = get_vector_index()
        await idx.upsert(
            [
                VectorDoc(
                    id=vec_id, tenant_id=tenant_id, text=text, vector=vec, metadata=metadata or {}
                )
            ]
        )
