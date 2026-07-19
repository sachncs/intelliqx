"""Knowledge / RAG Agent (Coordination).

Two-source hybrid retriever:

1. **Index** — FTS5 keyword + sqlite-vec vector search through the
   single :class:`intelliqx_okf.index.Index`. The same index covers
   OKF concepts, AST-graph nodes, and any ingested knowledge chunk.
2. **KG** — find knowledge-graph nodes whose attributes contain the
   query tokens (SQL ``LIKE``).

The lists are combined via weighted reciprocal-rank fusion (RRF,
``k=60``) and deduplicated by document id.
"""

from __future__ import annotations

from typing import Any, ClassVar

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory
from intelliqx_kg.graph import get_kg
from intelliqx_llm.client import get_llm_client
from intelliqx_okf import EmbeddingMismatchError, Hit, Index
from pydantic import BaseModel, ConfigDict, Field

RRF_K = 60


class KnowledgeRAGInput(BaseModel):
    """A RAG query.

    Attributes:
        query: The natural-language query.
        tenant_id: The owning tenant.
        top_k: Maximum number of documents to return.
        type_filter: Optional OKF ``type`` to restrict to.
        tag_filter: Optional tag that must appear in the concept.
    """

    model_config = ConfigDict(extra="forbid")

    query: str
    tenant_id: str
    top_k: int = 5
    type_filter: str | None = None
    tag_filter: str | None = None


class KnowledgeRAGDocument(BaseModel):
    """A single retrieval hit."""

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    score: float
    source: str  # index | kg | lexical


class KnowledgeRAGOutput(BaseModel):
    """Output payload for the RAG agent."""

    model_config = ConfigDict(extra="forbid")

    query: str
    documents: list[KnowledgeRAGDocument] = Field(default_factory=list)


class KnowledgeRAGAgent(AgentBase):
    """Three-source hybrid retriever over :class:`Index`, the KG, and episodic memory."""

    META = AgentMeta(
        name="knowledge_rag",
        category=AgentCategory.COORDINATION,
        version="0.4.0",
        description="Hybrid retriever: index + KG + lexical (RRF).",
    )
    INPUT_MODEL = KnowledgeRAGInput
    OUTPUT_MODEL = KnowledgeRAGOutput

    SOURCE_WEIGHTS: ClassVar[dict[str, float]] = {"index": 1.2, "kg": 0.5}

    def __init__(self, index: Index | None = None) -> None:
        super().__init__()
        self._index = index

    @property
    def index(self) -> Index:
        if self._index is None:
            from intelliqx_okf.index import open_index

            self._index = open_index()
        return self._index

    @classmethod
    def with_default_index(cls) -> KnowledgeRAGAgent:
        from intelliqx_okf.index import open_index

        return cls(open_index())

    @traced_agent("knowledge_rag")
    async def run(self, ctx: AgentContext, input: KnowledgeRAGInput) -> KnowledgeRAGOutput:
        tenant_id = ctx.tenant.tenant_id
        llm = get_llm_client()
        kg = get_kg()

        query_vec: list[float] | None = None
        try:
            query_vec = (await llm.embed([input.query], model="auto"))[0]
        except Exception:
            query_vec = None

        index_hits: list[KnowledgeRAGDocument] = []
        try:
            hits: list[Hit] = self.index.read(
                input.query,
                top=input.top_k * 3,
                type=input.type_filter,
                tag=input.tag_filter,
                query_embedding=query_vec,
                vector_weight=0.5 if query_vec is not None else 0.0,
            )
            for h in hits:
                text = (
                    h.concept.body
                    or h.concept.frontmatter.description
                    or h.concept.frontmatter.title
                    or ""
                )
                index_hits.append(
                    KnowledgeRAGDocument(
                        id=h.concept.concept_id, text=text, score=h.score, source="index"
                    )
                )
        except (FileNotFoundError, EmbeddingMismatchError):
            index_hits = []

        kg_hits: list[KnowledgeRAGDocument] = []
        if kg is not None:
            try:
                rows = kg.query(
                    "SELECT id, attrs FROM kg_nodes WHERE tenant_id = ? AND lower(coalesce(json_extract(attrs, '$.text'), '')) LIKE ?",
                    params=[tenant_id, f"%{input.query.lower()}%"],
                )
            except Exception:
                rows = None
            if rows is not None:
                for row in rows.rows[: input.top_k * 3]:
                    attrs = row.get("attrs") or {}
                    text = attrs.get("text") if isinstance(attrs, dict) else str(attrs)
                    kg_hits.append(
                        KnowledgeRAGDocument(
                            id=str(row.get("id", "")), text=text or "", score=0.5, source="kg"
                        )
                    )

        merged: dict[str, dict[str, Any]] = {}
        for source, candidates in (("index", index_hits), ("kg", kg_hits)):
            weight = self.SOURCE_WEIGHTS[source]
            for rank, doc in enumerate(candidates):
                bucket = merged.setdefault(doc.id, {"doc": doc, "rrf": 0.0})
                bucket["rrf"] += weight / (RRF_K + rank + 1)

        fused = sorted(merged.values(), key=lambda x: x["rrf"], reverse=True)[: input.top_k]
        return KnowledgeRAGOutput(
            query=input.query,
            documents=[
                KnowledgeRAGDocument(
                    id=item["doc"].id,
                    text=item["doc"].text,
                    score=item["rrf"],
                    source=item["doc"].source,
                )
                for item in fused
            ],
        )
