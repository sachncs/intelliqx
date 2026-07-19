"""Shared pytest fixtures.

The ``reset_singletons`` autouse fixture resets every module-level
singleton before each test so the suite is order-independent.
"""

from __future__ import annotations

import os

import pytest

# Set sane defaults before any application code is imported so the
# in-process adapters behave the same way in every test session.
os.environ.setdefault("INTELLIQX_LLM_BACKEND", "fake")
os.environ.setdefault("INTELLIQX_OBJECT_STORE", "memory")
os.environ.setdefault("INTELLIQX_OTEL", "0")


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset every module-level singleton to a clean state per test.

    Without this, tests that mutate a singleton (e.g. the metrics
    registry) would leak state to the next test. We call every
    known ``reset_*`` helper here.
    """
    from intelliqx_compute.runtime import reset_compute_runtime
    from intelliqx_events.bus import reset_event_bus
    from intelliqx_events.schemas import EventRegistry
    from intelliqx_kg.graph import reset_kg
    from intelliqx_llm.client import reset_llm_client
    from intelliqx_observability.metrics import reset_metrics
    from intelliqx_observability.tracing import reset_tracer
    from intelliqx_state.store import reset_state_store
    from intelliqx_storage.store import reset_object_store
    from intelliqx_tools.manager import reset_tool_manager

    reset_compute_runtime()
    reset_event_bus()
    reset_kg()
    reset_llm_client()
    reset_metrics()
    reset_tracer()
    reset_state_store()
    reset_object_store()
    reset_tool_manager()
    EventRegistry._contracts.clear()
    yield
