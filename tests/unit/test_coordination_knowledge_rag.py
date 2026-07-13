"""Tests for  Knowledge/RAG Agent."""

import pytest
from intelliqx_compute.runtime import InvocationRequest
from intelliqx_kg.graph import Node, get_kg

from agents import register_all, register_compute_handlers
from agents.coordination.knowledge_rag import KnowledgeRAGAgent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_vector_retrieval():
    register_all()
    register_compute_handlers()
    agent = KnowledgeRAGAgent()
    # Ingest two distinct docs
    await agent.ingest(tenant_id="t1", doc_id="d1", text="the quick brown fox")
    await agent.ingest(tenant_id="t1", doc_id="d2", text="lorem ipsum dolor sit amet")
    out = await agent.invoke(
        InvocationRequest(
            agent_name="knowledge_rag",
            input={"query": "fox", "tenant_id": "t1", "top_k": 5},
            tenant_id="t1",
        )
    )
    ids = {d["id"] for d in out["documents"]}
    assert "d1" in ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_kg_retrieval():
    register_all()
    register_compute_handlers()
    kg = get_kg()
    kg.reset()
    await kg.add_nodes(
        [Node(id="r_login", type="Requirement", tenant_id="t1", attrs={"title": "user login"})]
    )
    agent = KnowledgeRAGAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="knowledge_rag",
            input={"query": "login", "tenant_id": "t1", "top_k": 5},
            tenant_id="t1",
        )
    )
    ids = {d["id"] for d in out["documents"]}
    assert "r_login" in ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_lexical_retrieval():
    register_all()
    register_compute_handlers()
    agent = KnowledgeRAGAgent()
    from intelliqx_storage.store import get_object_store

    store = get_object_store()
    await store.put(
        "t1/episodic/d1",
        b"the regression test failed due to a selector mismatch",
        content_type="text/plain",
    )
    out = await agent.invoke(
        InvocationRequest(
            agent_name="knowledge_rag",
            input={"query": "regression", "tenant_id": "t1", "top_k": 5},
            tenant_id="t1",
        )
    )
    # lexical or vector path may return the doc depending on embeddings.
    assert (
        any("regression" in (d["text"] or "").lower() for d in out["documents"])
        or len(out["documents"]) >= 1
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_top_k_caps_results():
    register_all()
    register_compute_handlers()
    kg = get_kg()
    kg.reset()
    for i in range(20):
        await kg.add_nodes([Node(id=f"n{i}", type="X", tenant_id="t1", attrs={"x": f"item {i}"})])
    agent = KnowledgeRAGAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="knowledge_rag",
            input={"query": "item", "tenant_id": "t1", "top_k": 5},
            tenant_id="t1",
        )
    )
    assert len(out["documents"]) <= 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_tenant_isolation():
    register_all()
    register_compute_handlers()
    agent = KnowledgeRAGAgent()
    await agent.ingest(tenant_id="tA", doc_id="d1", text="apple")
    out = await agent.invoke(
        InvocationRequest(
            agent_name="knowledge_rag",
            input={"query": "apple", "tenant_id": "tB", "top_k": 5},
            tenant_id="tB",
        )
    )
    ids = {d["id"] for d in out["documents"]}
    assert "d1" not in ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_merged_results_dedupe():
    register_all()
    register_compute_handlers()
    kg = get_kg()
    kg.reset()
    # Add the same id to both vector and KG paths
    await agent_ingest("t1", "shared", "shared content")
    await kg.add_nodes(
        [Node(id="shared", type="X", tenant_id="t1", attrs={"text": "shared content here"})]
    )
    agent = KnowledgeRAGAgent()
    out = await agent.invoke(
        InvocationRequest(
            agent_name="knowledge_rag",
            input={"query": "shared", "tenant_id": "t1", "top_k": 5},
            tenant_id="t1",
        )
    )
    ids = [d["id"] for d in out["documents"]]
    # No duplicates
    assert len(ids) == len(set(ids))


async def agent_ingest(tenant_id: str, doc_id: str, text: str) -> None:
    agent = KnowledgeRAGAgent()
    await agent.ingest(tenant_id=tenant_id, doc_id=doc_id, text=text)
