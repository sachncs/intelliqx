"""Cross-cloud parity tests for aqip-state."""

import pytest
from aqip_state.aws import ElastiCacheStateStore
from aqip_state.gcp import MemorystoreStateStore
from aqip_state.modal import ModalDictStateStore
from aqip_state.store import InMemoryStateStore


@pytest.mark.cross_cloud
def test_aws_state_lazy_init():
    s = ElastiCacheStateStore(host="localhost")
    # Without redis SDK / endpoint, _available should be False
    assert not s._available


@pytest.mark.cross_cloud
def test_gcp_state_lazy_init():
    s = MemorystoreStateStore(host="localhost")
    assert not s._available


@pytest.mark.cross_cloud
def test_modal_state_lazy_init():
    s = ModalDictStateStore(name="aqip-test")
    assert not s._available


@pytest.mark.cross_cloud
@pytest.mark.asyncio
async def test_in_memory_state_contract_for_reference():
    """In-memory state store defines the contract other adapters must match."""
    s = InMemoryStateStore()
    await s.set("k", b"v")
    assert await s.get("k") == b"v"
    n = await s.incr("c")
    assert n == 1
    await s.hset("h", "f", "x")
    assert await s.hgetall("h") == {"f": "x"}
    await s.lpush("l", "y")
    assert await s.rpop("l") == "y"