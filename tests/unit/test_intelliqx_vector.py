"""Tests for intelliqx-vector."""

import pytest
from intelliqx_vector.index import InMemoryVectorIndex, VectorDoc, get_vector_index


def random_vec(seed: int, dim: int = 8) -> list[float]:
    import random

    rnd = random.Random(seed)
    return [rnd.random() * 2 - 1 for _ in range(dim)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_and_count():
    idx = InMemoryVectorIndex(dim=8)
    docs = [VectorDoc(id=f"d{i}", tenant_id="t1", vector=random_vec(i, 8)) for i in range(5)]
    n = await idx.upsert(docs)
    assert n == 5
    assert await idx.count() == 5
    assert await idx.count(tenant_id="t1") == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dim_mismatch_raises():
    idx = InMemoryVectorIndex(dim=8)
    with pytest.raises(ValueError):
        await idx.upsert([VectorDoc(id="d1", tenant_id="t1", vector=[0.0, 0.1])])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_tenant_isolation():
    idx = InMemoryVectorIndex(dim=8)
    a = VectorDoc(id="a", tenant_id="t1", vector=random_vec(1, 8))
    b = VectorDoc(id="b", tenant_id="t2", vector=random_vec(1, 8))
    await idx.upsert([a, b])
    res = await idx.search(random_vec(1, 8), top_k=5, tenant_id="t1")
    assert all(r.id == "a" for r in res)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_returns_top_k():
    idx = InMemoryVectorIndex(dim=8)
    docs = [VectorDoc(id=f"d{i}", tenant_id="t1", vector=random_vec(i, 8)) for i in range(20)]
    await idx.upsert(docs)
    res = await idx.search(random_vec(0, 8), top_k=5)
    assert len(res) == 5
    # scores descending
    scores = [r.score for r in res]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete():
    idx = InMemoryVectorIndex(dim=8)
    await idx.upsert([VectorDoc(id="d1", tenant_id="t1", vector=random_vec(1, 8))])
    n = await idx.delete(["d1"])
    assert n == 1
    assert await idx.count() == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recall_against_brute_force():
    """Top-K results must include the same IDs as brute-force cosine similarity."""

    dim = 32
    n = 200
    k = 10
    idx = InMemoryVectorIndex(dim=dim)
    docs = [
        VectorDoc(id=f"d{i}", tenant_id="t1", vector=random_vec(i + 1000, dim)) for i in range(n)
    ]
    await idx.upsert(docs)
    query = random_vec(9999, dim)
    res_idx = await idx.search(query, top_k=k)

    # brute force
    def cos(a, b):
        import math

        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = math.sqrt(sum(x * x for x in a)) + 1e-12
        nb = math.sqrt(sum(x * x for x in b)) + 1e-12
        return dot / (na * nb)

    brute = sorted(((cos(query, d.vector), d.id) for d in docs), key=lambda x: -x[0])[:k]
    brute_ids = {bid for _, bid in brute}
    idx_ids = {r.id for r in res_idx}
    # recall@10 should be high (≥0.8) for cosine on random vectors
    overlap = len(brute_ids & idx_ids)
    assert overlap >= int(0.8 * k)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_singleton_default():
    idx = get_vector_index()
    assert isinstance(idx, InMemoryVectorIndex)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_metadata_filter():
    idx = InMemoryVectorIndex(dim=8)
    await idx.upsert(
        [
            VectorDoc(id="x", tenant_id="t1", vector=random_vec(1, 8), metadata={"k": "a"}),
            VectorDoc(id="y", tenant_id="t1", vector=random_vec(2, 8), metadata={"k": "b"}),
        ]
    )
    res = await idx.search(random_vec(1, 8), top_k=5, filter_metadata={"k": "a"})
    assert len(res) == 1
    assert res[0].id == "x"
