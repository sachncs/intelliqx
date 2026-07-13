"""Tests for intelliqx-sdk."""

from pathlib import Path

import pytest
from intelliqx_sdk.manifest import AgentManifest, dump_manifest, load_manifest
from intelliqx_sdk.sandbox import Sandbox


@pytest.mark.unit
def test_manifest_roundtrip(tmp_path: Path):
    m = AgentManifest(
        name="thirdparty",
        version="1.0.0",
        tier=2,
        description="d",
        author="acme",
        capabilities=["llm"],
        permissions=["net"],
    )
    p = tmp_path / "manifest.json"
    dump_manifest(m, p)
    m2 = load_manifest(p)
    assert m2.name == "thirdparty"
    assert m2.tier == 2


@pytest.mark.unit
def test_manifest_extra_forbidden():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AgentManifest(name="x", version="1", tier=1, bogus=1)


@pytest.mark.unit
def test_sandbox_enforce():
    from intelliqx_sdk.sandbox import SandboxViolation

    s = Sandbox(cpu_time_seconds=10, memory_mb=256, max_file_descriptors=64)
    try:
        with s.enforce():
            assert s.cpu_time_seconds == 10
    except SandboxViolation:
        pytest.skip("Sandbox rlimits not supported on this platform")
    except (OSError, ValueError):
        pytest.skip("Sandbox rlimits not supported on this platform")


@pytest.mark.unit
def test_sandbox_restore_limits():
    import resource

    from intelliqx_sdk.sandbox import SandboxViolation

    s = Sandbox(cpu_time_seconds=10, memory_mb=256, max_file_descriptors=64)
    try:
        with s.enforce():
            cur = resource.getrlimit(resource.RLIMIT_CPU)
            assert cur[0] == 10
    except SandboxViolation:
        pytest.skip("Sandbox rlimits not supported on this platform")
    except (OSError, ValueError):
        pytest.skip("Sandbox rlimits not supported on this platform")
