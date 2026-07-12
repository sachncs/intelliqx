"""Smoke tests for library imports."""

import importlib

import pytest

LIBS = [
    "aqip_core",
    "aqip_portability",
    "aqip_events",
    "aqip_storage",
    "aqip_vector",
    "aqip_kg",
    "aqip_state",
    "aqip_llm",
    "aqip_compute",
    "aqip_observability",
    "aqip_tools",
    "aqip_agents",
    "aqip_tenant",
    "aqip_sdk",
]


@pytest.mark.unit
@pytest.mark.parametrize("lib", LIBS)
def test_library_imports(lib):
    mod = importlib.import_module(lib)
    assert mod is not None