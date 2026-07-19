"""Observability for IntelliqX.

Three pillars: structured logs (Loguru), in-process metrics
(counter / gauge / histogram), distributed traces
(OpenTelemetry with start_as_current_span and an optional OTLP/HTTP
exporter). Singletons expose ``get_logger`` / ``get_metrics`` /
``get_tracer``; tests use ``reset_logging`` / ``reset_tracer`` to
return to a clean world.
"""

from intelliqx_observability.logging import (
    bind_context,
    configure_logging,
    get_logger,
    reset_logging,
)
from intelliqx_observability.metrics import Counter, Gauge, Histogram, MetricsRegistry, get_metrics
from intelliqx_observability.tracing import Tracer, configure_tracing, get_tracer

__all__ = [
    "Counter",
    "Gauge",
    "Histogram",
    "MetricsRegistry",
    "Tracer",
    "bind_context",
    "configure_logging",
    "configure_tracing",
    "get_logger",
    "get_metrics",
    "get_tracer",
    "reset_logging",
]
