"""Knowledge / RAG Agent (Tier 1).

Hybrid retriever: vector similarity (zvec) + lexical match on the
knowledge graph (DuckDB on Parquet) + sparse lexical match on the
episodic memory (object store).

The three sources are scored independently and merged in
``run``. The final ranking deduplicates by document id (keeping the
highest score) and truncates to ``top_k``.
"""

from __future__ import annotations

from typing import Any

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_kg.graph import get_kg
from intelliqx_llm.client import get_llm_client
from intelliqx_storage.store import get_object_store
from intelliqx_vector.index import VectorDoc, get_vector_index
from pydantic import BaseModel, ConfigDict, Field


class RAGQuery(BaseModel):
    """A RAG query.

    Attributes:
        query: The natural-language query.
        tenant_id: The owning tenant.
        top_k: Maximum number of documents to return.
        namespaces: Reserved for future use; the current
            implementation searches all sources.
    """

    model_config = ConfigDict(extra="forbid")

    query: str
    tenant_id: str
    top_k: int = 5
    namespaces: list[str] = Field(default_factory=lambda: ["docs", "code", "episodic"])


class RAGDocument(BaseModel):
    """A single retrieval hit.

    ``source`` is one of ``"vector"``, ``"kg"``, or ``"lexical"``.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    score: float
    source: str  # vector | kg | lexical


class RAGOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    documents: list[RAGDocument] = Field(default_factory=list)


class KnowledgeRAGAgent(AgentBase):
    """Three-source hybrid retriever.

    Sources, in order:
        1. **Vector** — embed the query and run a zvec ANN search.
        2. **KG**     — find nodes whose ``attrs`` contain the
           query tokens (SQL ``LIKE``).
        3. **Lexical** — list the tenant's episodic memory in the
           object store and rank by term frequency.

    The merge is a max-by-id operation; if a document appears in
    multiple sources, we keep the highest score. The final list is
    sorted by descending score and truncated to ``top_k``.
    """

    META = AgentMeta(
        name="knowledge_rag",
        tier=1,
        version="0.1.0",
        description="Hybrid retriever: vector + KG + lexical.",
    )
    INPUT_MODEL = RAGQuery
    OUTPUT_MODEL = RAGOutput

    @traced_agent("knowledge_rag")
    async def run(self, ctx: AgentContext, input: RAGQuery) -> RAGOutput:
        tenant_id = ctx.tenant.tenant_id
        llm = get_llm_client()
        vec_index = get_vector_index()
        kg = get_kg()
        store = get_object_store()

        # 1) Vector search — embed query and search zvec.
        query_vec = (await llm.embed([input.query], model="auto"))[0]
        vec_results = await vec_index.search(
            query_vec, top_k=input.top_k, tenant_id=tenant_id
        )
        out: list[RAGDocument] = []
        for r in vec_results:
            out.append(
                RAGDocument(
                    id=r.id,
                    text=r.text or "",
                    score=r.score,
                    source="vector",
                )
            )

        # 2) KG neighbors — find entities whose text contains query
        # tokens. The constant 0.5 score reflects that the KG hit
        # is "exact substring" rather than semantically ranked.
        kg_rows = kg.query(
            "SELECT id, type, attrs FROM kg_nodes WHERE tenant_id = ? AND lower(attrs) LIKE ?",
            params=[tenant_id, f"%{input.query.lower()}%"],
        )
        for row in kg_rows.rows[: input.top_k]:
            text = str(row.get("attrs", ""))
            out.append(
                RAGDocument(
                    id=str(row["id"]),
                    text=text,
                    score=0.5,  # constant score for KG hits
                    source="kg",
                )
            )

        # 3) Lexical — search episodic memory in the object store.
        terms = [t.lower() for t in input.query.split() if t]
        scored: list[RAGDocument] = []
        async for key in store.list(f"{tenant_id}/episodic/"):
            try:
                blob = await store.get(key)
            except Exception:
                continue
            text = blob.decode("utf-8", errors="ignore")
            hits = sum(text.lower().count(t) for t in terms)
            if hits > 0:
                scored.append(
                    RAGDocument(
                        id=key,
                        text=text[:400],
                        score=float(hits),
                        source="lexical",
                    )
                )
        scored.sort(key=lambda r: -r.score)
        out.extend(scored[: input.top_k])

        # Dedupe by id, keep highest score.
        merged: dict[str, RAGDocument] = {}
        for d in out:
            if d.id not in merged or merged[d.id].score < d.score:
                merged[d.id] = d
        docs = sorted(merged.values(), key=lambda r: -r.score)[: input.top_k]
        return RAGOutput(query=input.query, documents=docs)

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
                    id=doc_id,
                    tenant_id=tenant_id,
                    text=text,
                    vector=vec,
                    metadata=metadata or {},
                )
            ]
        )
