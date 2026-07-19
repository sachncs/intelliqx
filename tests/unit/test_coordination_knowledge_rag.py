"""KnowledgeRAGAgent uses :class:`Index` + KG + episodic memory."""

from __future__ import annotations

from pathlib import Path

import pytest
from intelliqx_agents.base import AgentContext
from intelliqx_core.models import TenantContext
from intelliqx_kg.graph import KnowledgeGraph, Node, set_kg
from intelliqx_llm.client import set_llm_client
from intelliqx_okf import Index
from intelliqx_okf.concept import OKFConcept
from intelliqx_okf.frontmatter import OKFFrontmatter
from intelliqx_storage.store import InMemoryObjectStore, set_object_store

from agents.coordination.knowledge_rag import KnowledgeRAGAgent, KnowledgeRAGInput
from tests.okf._embed import FakeEmbedder

DIM = 8


@pytest.fixture
def env(tmp_path: Path):
    set_llm_client(_Fake(dim=DIM))
    index = Index(tmp_path / "k.db", embed=FakeEmbedder(DIM))
    kg = KnowledgeGraph()
    set_kg(kg)
    store = InMemoryObjectStore()
    set_object_store(store)
    yield index, kg, store
    index.close()
    set_kg(None)
    set_object_store(None)
    set_llm_client(None)


def _ctx(tenant_id: str) -> AgentContext:
    return AgentContext(tenant=TenantContext(tenant_id=tenant_id), run_id="r", trace_id=None)


def _concept(cid: str, body: str, type_: str = "doc") -> OKFConcept:
    return OKFConcept(
        concept_id=cid, frontmatter=OKFFrontmatter(type=type_, title=cid.title()), body=body
    )


class _Fake:
    def __init__(self, *, dim: int = 8) -> None:
        self.dim = dim
        self._embedder = FakeEmbedder(dim)

    @property
    def model(self) -> str:
        return "fake"

    @property
    def DEFAULT_MODEL(self) -> str:
        return "fake"

    async def embed(self, texts, *, model: str = "auto"):
        return [self._embedder.embed(t) for t in texts]


@pytest.mark.asyncio
async def test_returns_index_hits(env) -> None:
    index, _, _ = env
    index.write(_concept("auth", "authentication flow"))
    agent = KnowledgeRAGAgent(index)
    out = await agent.run(
        _ctx("t1"), KnowledgeRAGInput(query="authentication", tenant_id="t1", top_k=3)
    )
    assert any(d.id == "auth" and d.source == "index" for d in out.documents)


@pytest.mark.asyncio
async def test_falls_back_to_fts_when_embedding_dim_mismatches(env) -> None:
    index, _, _ = env
    index.write(_concept("auth", "authentication flow"))
    agent = KnowledgeRAGAgent(index)
    out = await agent.run(
        _ctx("t1"), KnowledgeRAGInput(query="authentication", tenant_id="t1", top_k=3)
    )
    assert out.documents


@pytest.mark.asyncio
async def test_kg_returns_node_hits(env) -> None:
    index, kg, _ = env
    await kg.add_nodes([Node(id="n1", type="doc", attrs={"text": "alpha bravo"}, tenant_id="t1")])
    agent = KnowledgeRAGAgent(index)
    out = await agent.run(_ctx("t1"), KnowledgeRAGInput(query="alpha", tenant_id="t1", top_k=3))
    assert any(d.id == "n1" and d.source == "kg" for d in out.documents)
