"""Tests for intelliqx-portability."""

import pytest
from intelliqx_core.errors import CloudConfigError
from intelliqx_core.models import CloudProvider
from intelliqx_portability.adapter import get_adapter, reset_adapter_cache
from intelliqx_portability.adapters.aws import AWSAdapter
from intelliqx_portability.adapters.gcp import GCPAdapter
from intelliqx_portability.adapters.local import LocalAdapter
from intelliqx_portability.adapters.modal import ModalAdapter
from intelliqx_portability.config import CloudConfig


@pytest.mark.unit
def test_config_defaults():
    c = CloudConfig(provider=CloudProvider.AWS)
    assert c.region == "us-east-1"
    assert not c.is_local


@pytest.mark.unit
def test_config_provider_checks():
    aws = CloudConfig(provider=CloudProvider.AWS)
    gcp = CloudConfig(provider=CloudProvider.GCP)
    modal = CloudConfig(provider=CloudProvider.MODAL)
    local = CloudConfig(provider=CloudProvider.LOCAL)
    assert aws.is_aws
    assert gcp.is_gcp
    assert modal.is_modal
    assert local.is_local


@pytest.mark.unit
def test_get_adapter_local(monkeypatch):
    monkeypatch.setenv("INTELLIQX_CLOUD", "local")
    reset_adapter_cache()
    a = get_adapter()
    assert isinstance(a, LocalAdapter)
    assert a.short_name() == "local"


@pytest.mark.unit
def test_get_adapter_aws(monkeypatch):
    monkeypatch.setenv("INTELLIQX_CLOUD", "aws")
    reset_adapter_cache()
    a = get_adapter()
    assert isinstance(a, AWSAdapter)


@pytest.mark.unit
def test_get_adapter_gcp(monkeypatch):
    monkeypatch.setenv("INTELLIQX_CLOUD", "gcp")
    reset_adapter_cache()
    a = get_adapter()
    assert isinstance(a, GCPAdapter)


@pytest.mark.unit
def test_get_adapter_modal(monkeypatch):
    monkeypatch.setenv("INTELLIQX_CLOUD", "modal")
    reset_adapter_cache()
    a = get_adapter()
    assert isinstance(a, ModalAdapter)


@pytest.mark.unit
def test_unknown_cloud(monkeypatch):
    monkeypatch.setenv("INTELLIQX_CLOUD", "wat")
    reset_adapter_cache()
    with pytest.raises(CloudConfigError):
        get_adapter()


@pytest.mark.unit
def test_adapter_singleton(monkeypatch):
    monkeypatch.setenv("INTELLIQX_CLOUD", "local")
    reset_adapter_cache()
    assert get_adapter() is get_adapter()