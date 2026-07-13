"""Contract tests: portability layer guarantees interfaces are uniform across adapters."""

from pathlib import Path

import pytest
from intelliqx_events.bus import EventBus, InMemoryEventBus
from intelliqx_state.store import InMemoryStateStore, StateStore
from intelliqx_storage.store import InMemoryObjectStore, LocalFileSystemObjectStore, ObjectStore
from intelliqx_vector.index import InMemoryVectorIndex, VectorIndex


@pytest.mark.contract
@pytest.mark.asyncio
async def test_object_store_contract(tmp_path: Path):
    """Both InMemory and LocalFileSystem stores must satisfy the same contract."""

    async def check_store(s: ObjectStore) -> None:
        await s.put("k", b"v")
        assert await s.get("k") == b"v"
        assert await s.exists("k")
        await s.delete("k")
        assert not await s.exists("k")

    await check_store(InMemoryObjectStore())
    await check_store(LocalFileSystemObjectStore(tmp_path))


@pytest.mark.contract
@pytest.mark.asyncio
async def test_state_store_contract():
    async def check_store(s: StateStore) -> None:
        await s.set("k", b"v")
        assert await s.get("k") == b"v"
        n = await s.incr("c")
        assert n == 1
        await s.hset("h", "f", "v")
        assert await s.hgetall("h") == {"f": "v"}
        await s.lpush("l", "x")
        assert await s.rpop("l") == "x"

    await check_store(InMemoryStateStore())


@pytest.mark.contract
@pytest.mark.asyncio
async def test_vector_index_contract():
    async def check_index(i: VectorIndex) -> None:
        await i.upsert([_doc("a", [1.0, 0.0, 0.0, 0.0]), _doc("b", [0.0, 1.0, 0.0, 0.0])])
        res = await i.search([1.0, 0.0, 0.0, 0.0], top_k=1)
        assert res[0].id == "a"
        await i.delete(["a", "b"])
        assert await i.count() == 0

    await check_index(InMemoryVectorIndex(dim=4))


@pytest.mark.contract
@pytest.mark.asyncio
async def test_event_bus_contract():
    async def check_bus(b: EventBus) -> None:
        received = []

        def h(e):
            received.append(e)

        b.subscribe("t", h)
        from intelliqx_core.events import BaseEvent, EventMetadata

        md = EventMetadata(tenant_id="t1", produced_by="c")
        await b.publish("t", BaseEvent(detail_type="T", metadata=md))
        assert len(received) == 1

    await check_bus(InMemoryEventBus())


def _doc(id: str, vec: list[float]):
    from intelliqx_vector.index import VectorDoc

    return VectorDoc(id=id, tenant_id="t1", vector=vec)
