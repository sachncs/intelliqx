"""Tests for intelliqx-vector sqlite-vec-backed index."""

from pathlib import Path

import pytest

try:
    import sqlitevector  # noqa: F401

    HAS_SQLITE_VEC = True
except ImportError:
    HAS_SQLITE_VEC = False

from intelliqx_vector.index import VectorDoc
from intelliqx_vector.sqlite_vec_index import SqliteVecIndex

pytestmark = pytest.mark.skipif(not HAS_SQLITE_VEC, reason="sqlite-vec not available")


def vector(*values: float) -> list[float]:
    return list(values)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_and_count(tmp_path: Path):
    idx = SqliteVecIndex(dim=4, db_path=str(tmp_path / "test.db"))
    docs = [
        VectorDoc(id="a", tenant_id="t1", vector=vector(1.0, 0.0, 0.0, 0.0)),
        VectorDoc(id="b", tenant_id="t1", vector=vector(0.0, 1.0, 0.0, 0.0)),
    ]
    n = await idx.upsert(docs)
    assert n == 2
    assert await idx.count() == 2
    assert await idx.count(tenant_id="t1") == 2
    assert await idx.count(tenant_id="t2") == 0
    idx.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_update_replaces_vector(tmp_path: Path):
    idx = SqliteVecIndex(dim=4, db_path=str(tmp_path / "test.db"))
    await idx.upsert([VectorDoc(id="a", tenant_id="t1", vector=vector(1.0, 0.0, 0.0, 0.0))])
    await idx.upsert([VectorDoc(id="a", tenant_id="t1", vector=vector(0.0, 0.0, 1.0, 0.0))])
    res = await idx.search(vector(0.0, 0.0, 1.0, 0.0), top_k=1)
    assert len(res) == 1
    assert res[0].id == "a"
    assert res[0].score > 0.9
    idx.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dim_mismatch_raises(tmp_path: Path):
    idx = SqliteVecIndex(dim=4, db_path=str(tmp_path / "test.db"))
    with pytest.raises(ValueError, match="dim mismatch"):
        await idx.upsert([VectorDoc(id="a", tenant_id="t1", vector=vector(1.0, 0.0))])
    with pytest.raises(ValueError, match="dim mismatch"):
        await idx.search(vector(1.0, 0.0), top_k=1)
    idx.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_cosine_similarity(tmp_path: Path):
    idx = SqliteVecIndex(dim=4, db_path=str(tmp_path / "test.db"))
    await idx.upsert(
        [
            VectorDoc(id="same", tenant_id="t1", vector=vector(1.0, 0.0, 0.0, 0.0)),
            VectorDoc(id="ortho", tenant_id="t1", vector=vector(0.0, 1.0, 0.0, 0.0)),
        ]
    )
    res = await idx.search(vector(1.0, 0.0, 0.0, 0.0), top_k=2)
    assert len(res) == 2
    scores = {r.id: r.score for r in res}
    assert scores["same"] > 0.9
    assert scores["ortho"] < 0.1
    assert scores["same"] > scores["ortho"]
    idx.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tenant_isolation(tmp_path: Path):
    idx = SqliteVecIndex(dim=4, db_path=str(tmp_path / "test.db"))
    await idx.upsert(
        [
            VectorDoc(id="a", tenant_id="t1", vector=vector(1.0, 0.0, 0.0, 0.0)),
            VectorDoc(id="b", tenant_id="t2", vector=vector(1.0, 0.0, 0.0, 0.0)),
        ]
    )
    res = await idx.search(vector(1.0, 0.0, 0.0, 0.0), top_k=5, tenant_id="t1")
    assert all(r.id == "a" for r in res)
    assert len(res) == 1
    idx.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_metadata_filter(tmp_path: Path):
    idx = SqliteVecIndex(dim=4, db_path=str(tmp_path / "test.db"))
    await idx.upsert(
        [
            VectorDoc(
                id="a", tenant_id="t1", vector=vector(1.0, 0.0, 0.0, 0.0), metadata={"env": "prod"}
            ),
            VectorDoc(
                id="b", tenant_id="t1", vector=vector(1.0, 0.0, 0.0, 0.0), metadata={"env": "staging"}
            ),
        ]
    )
    res = await idx.search(vector(1.0, 0.0, 0.0, 0.0), top_k=5, filter_metadata={"env": "prod"})
    assert len(res) == 1
    assert res[0].id == "a"
    idx.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete(tmp_path: Path):
    idx = SqliteVecIndex(dim=4, db_path=str(tmp_path / "test.db"))
    await idx.upsert([VectorDoc(id="a", tenant_id="t1", vector=vector(1.0, 0.0, 0.0, 0.0))])
    n = await idx.delete(["a"])
    assert n == 1
    assert await idx.count() == 0
    idx.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persistence_reopen(tmp_path: Path):
    db = str(tmp_path / "persist.db")
    idx1 = SqliteVecIndex(dim=4, db_path=db)
    await idx1.upsert([VectorDoc(id="a", tenant_id="t1", vector=vector(1.0, 0.0, 0.0, 0.0))])
    idx1.close()
    idx2 = SqliteVecIndex(dim=4, db_path=db)
    assert await idx2.count() == 1
    res = await idx2.search(vector(1.0, 0.0, 0.0, 0.0), top_k=1)
    assert len(res) == 1
    assert res[0].id == "a"
    idx2.close()


@pytest.mark.unit
def test_wrong_dim_raises_on_reopen(tmp_path: Path):
    db = str(tmp_path / "dim.db")
    idx1 = SqliteVecIndex(dim=4, db_path=db)
    idx1.close()
    with pytest.raises(ValueError, match="Dimension mismatch"):
        SqliteVecIndex(dim=8, db_path=db)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_upsert(tmp_path: Path):
    idx = SqliteVecIndex(dim=4, db_path=str(tmp_path / "test.db"))
    n = await idx.upsert([])
    assert n == 0
    idx.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_delete(tmp_path: Path):
    idx = SqliteVecIndex(dim=4, db_path=str(tmp_path / "test.db"))
    n = await idx.delete([])
    assert n == 0
    idx.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_singleton_export():
    from intelliqx_vector.index import get_vector_index, reset_vector_index

    get_vector_index()

    reset_vector_index()
    idx2 = get_vector_index()
    assert not isinstance(idx2, SqliteVecIndex)
