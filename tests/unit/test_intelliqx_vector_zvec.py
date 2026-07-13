"""Tests for intelliqx-vector zvec-backed index."""

from pathlib import Path

import pytest
from intelliqx_storage.store import InMemoryObjectStore
from intelliqx_vector.zvec_index import ZvecIndex


@pytest.mark.unit
@pytest.mark.asyncio
async def test_zvec_upsert_and_search(tmp_path: Path):
    storage = InMemoryObjectStore()
    idx = ZvecIndex(dim=16, storage=storage, local_root=tmp_path)
    docs = [
        idx_doc("a", v=[1.0, 0.0] + [0.0] * 14),
        idx_doc("b", v=[0.0, 1.0] + [0.0] * 14),
        idx_doc("c", v=[0.5, 0.5] + [0.0] * 14),
    ]
    n = await idx.upsert(docs)
    assert n == 3
    res = await idx.search([1.0, 0.0] + [0.0] * 14, top_k=2)
    assert len(res) >= 1
    # top hit should be 'a' (closest to query)
    assert res[0].id == "a"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_zvec_persistence_manifest(tmp_path: Path):
    storage = InMemoryObjectStore()
    ZvecIndex(dim=8, storage=storage, local_root=tmp_path)
    # manifest should be persisted
    keys = [k async for k in storage.list("")]
    assert any(k.endswith("_manifest.json") for k in keys)


def idx_doc(i, v):
    from intelliqx_vector.index import VectorDoc

    return VectorDoc(id=i, tenant_id="t1", vector=v, text=f"doc {i}", metadata={"i": i})
