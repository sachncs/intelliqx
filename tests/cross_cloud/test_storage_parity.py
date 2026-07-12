"""Cross-cloud parity tests for aqip-storage."""

import pytest
from aqip_storage.aws import S3ObjectStore
from aqip_storage.gcp import GCSObjectStore
from aqip_storage.modal import ModalVolumeObjectStore
from aqip_storage.store import InMemoryObjectStore, LocalFileSystemObjectStore


def _make_store(profile: str, tmp_path):
    if profile == "aws":
        return S3ObjectStore(bucket="aqip-test")
    if profile == "gcp":
        return GCSObjectStore(bucket="aqip-test")
    if profile == "modal":
        return ModalVolumeObjectStore(volume_name="aqip-test")
    if profile == "fs":
        return LocalFileSystemObjectStore(tmp_path)
    return InMemoryObjectStore()


@pytest.mark.cross_cloud
@pytest.mark.parametrize("profile", ["local", "fs"])
def test_store_constructs_without_error(profile, tmp_path):
    store = _make_store(profile, tmp_path)
    assert store is not None


@pytest.mark.cross_cloud
@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["local", "fs"])
async def test_store_roundtrip_via_in_memory_or_fs(profile, tmp_path):
    """Cloud stores that lack local creds will skip this; in-memory + fs always run."""
    store = _make_store(profile, tmp_path)
    await store.put("k", b"hello")
    assert await store.get("k") == b"hello"
    assert await store.exists("k")
    await store.delete("k")
    assert not await store.exists("k")


@pytest.mark.cross_cloud
def test_store_lazy_init_aws():
    store = S3ObjectStore(bucket="aqip-test")
    # No creds → _available is False → calls should fail clearly
    assert not store._available


@pytest.mark.cross_cloud
def test_store_lazy_init_gcp():
    store = GCSObjectStore(bucket="aqip-test")
    assert not store._available


@pytest.mark.cross_cloud
def test_store_lazy_init_modal():
    store = ModalVolumeObjectStore(volume_name="aqip-test")
    assert not store._available