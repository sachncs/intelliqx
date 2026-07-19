"""Smoke tests for library imports."""

import importlib

import pytest

LIBS = [
    "intelliqx_core",
    "intelliqx_events",
    "intelliqx_storage",
    "intelliqx_kg",
    "intelliqx_state",
    "intelliqx_llm",
    "intelliqx_compute",
    "intelliqx_observability",
    "intelliqx_tools",
    "intelliqx_agents",
    "intelliqx_tenant",
    "intelliqx_sdk",
    "intelliqx_okf",
]


@pytest.mark.unit
@pytest.mark.parametrize("lib", LIBS)
def test_library_imports(lib):
    mod = importlib.import_module(lib)
    assert mod is not None
