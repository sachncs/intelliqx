"""Observability for AQIP.

The observability stack has three pillars:

* **Logs** (structlog) — structured, JSON-or-console, with
  per-context fields merged in via ``structlog.contextvars``.
* **Metrics** (counter / gauge / histogram) — in-process, thread-safe,
  and exported as plain dicts for tests and simple scrape endpoints.
* **Traces** (OpenTelemetry) — span-based, with a thin Pythonic
  wrapper that keeps agent code free of OTel types in call sites.

Singletons are exposed by ``get_logger``, ``get_metrics``, and
``get_tracer``. Tests reset them via the matching ``reset_*`` helpers
to guarantee a clean world per test.
"""

from intelliqx_observability.logging import configure_logging, get_logger
from intelliqx_observability.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    get_metrics,
)
from intelliqx_observability.tracing import Tracer, configure_tracing, get_tracer

__all__ = [
    "Counter",
    "Gauge",
    "Histogram",
    "MetricsRegistry",
    "Tracer",
    "configure_logging",
    "configure_tracing",
    "get_logger",
    "get_metrics",
    "get_tracer",
]
