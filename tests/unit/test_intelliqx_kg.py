"""Tests for aqip-kg."""

import pytest
from intelliqx_kg.graph import Edge, KnowledgeGraph, Node, get_kg


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_nodes_and_query():
    kg = KnowledgeGraph()
    n = await kg.add_nodes(
        [
            Node(id="r1", type="Requirement", tenant_id="t1", attrs={"priority": "high"}),
            Node(id="r2", type="Requirement", tenant_id="t1", attrs={"priority": "low"}),
        ]
    )
    assert n == 2
    assert kg.node_count() == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_neighbors_out():
    kg = KnowledgeGraph()
    await kg.add_nodes(
        [
            Node(id="t1", type="TestCase", tenant_id="t1"),
            Node(id="t2", type="TestCase", tenant_id="t1"),
            Node(id="r1", type="Requirement", tenant_id="t1"),
        ]
    )
    await kg.add_edges(
        [
            Edge(src="t1", dst="r1", type="VALIDATES", tenant_id="t1"),
            Edge(src="t2", dst="r1", type="VALIDATES", tenant_id="t1"),
        ]
    )
    res = kg.neighbors("r1", tenant_id="t1", direction="in")
    ids = {row["id"] for row in res.rows}
    assert ids == {"t1", "t2"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_with_sql():
    kg = KnowledgeGraph()
    await kg.add_nodes(
        [
            Node(id="a", type="X", tenant_id="t1", attrs={"v": 1}),
            Node(id="b", type="X", tenant_id="t2", attrs={"v": 2}),
        ]
    )
    res = kg.query("SELECT id FROM kg_nodes WHERE tenant_id = ?", params=["t1"])
    assert res.row_count == 1
    assert res.rows[0]["id"] == "a"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_node_count_by_tenant():
    kg = KnowledgeGraph()
    await kg.add_nodes(
        [
            Node(id="a", type="X", tenant_id="t1"),
            Node(id="b", type="X", tenant_id="t1"),
            Node(id="c", type="X", tenant_id="t2"),
        ]
    )
    assert kg.node_count() == 3
    assert kg.node_count(tenant_id="t1") == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_edge_count():
    kg = KnowledgeGraph()
    await kg.add_nodes([Node(id="a", type="X", tenant_id="t1"), Node(id="b", type="X", tenant_id="t1")])
    await kg.add_edges([Edge(src="a", dst="b", type="REL", tenant_id="t1")])
    assert kg.edge_count() == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persists_to_object_store():
    from intelliqx_storage.store import InMemoryObjectStore

    storage = InMemoryObjectStore()
    kg = KnowledgeGraph(storage=storage)
    await kg.add_nodes([Node(id="n1", type="X", tenant_id="t1")])
    keys = [k async for k in storage.list("")]
    assert any(k.endswith(".parquet") for k in keys)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_neighbors_edge_type_filter():
    kg = KnowledgeGraph()
    await kg.add_nodes(
        [
            Node(id="x", type="X", tenant_id="t1"),
            Node(id="y", type="Y", tenant_id="t1"),
        ]
    )
    await kg.add_edges(
        [
            Edge(src="x", dst="y", type="A", tenant_id="t1"),
            Edge(src="x", dst="y", type="B", tenant_id="t1"),
        ]
    )
    res = kg.neighbors("x", tenant_id="t1", direction="out", edge_type="A")
    assert res.row_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_kg_singleton():
    kg = get_kg()
    assert isinstance(kg, KnowledgeGraph)