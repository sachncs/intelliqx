"""OpenTelemetry tracing for IntelliqX.

Thin ``Tracer`` / ``SpanProxy`` wrapper so agent code does not
import ``opentelemetry.*`` types directly. Spans use
``start_as_current_span`` so nested calls inherit trace context,
record wall-clock ``duration_ms`` in ``finally``, and mark the span
``ERROR`` when :meth:`SpanProxy.set_status_error` is called or an
exception escapes the ``with`` block.

Span export is opt-in: when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set,
the SDK is configured with an OTLP/HTTP exporter +
``BatchSpanProcessor``. Without an endpoint spans are recorded
in-memory only. ``opentelemetry-instrumentation-logging`` is
deliberately not wired up — correlation flows through the
``trace_id`` / ``span_id`` injected by the logging stack.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

OTLP_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"


def configure_tracing(service_name: str = "intelliqx", *, otlp_endpoint: str | None = None) -> None:
    """Configure the OTel SDK. OTLP/HTTP only fires when an endpoint is supplied."""
    endpoint = otlp_endpoint or os.environ.get(OTLP_ENDPOINT_ENV)
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)


class Tracer:
    """Wrapper around the SDK tracer."""

    def __init__(self) -> None:
        if os.environ.get("INTELLIQX_OTEL") == "1":
            configure_tracing()
        self.tracer = trace.get_tracer("intelliqx")

    @contextmanager
    def span(self, name: str, **attrs: Any):
        with self.tracer.start_as_current_span(name, attributes=_otel_attrs(attrs)) as span:
            start = time.monotonic()
            try:
                yield SpanProxy(span)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
                raise
            finally:
                span.set_attribute("duration_ms", int((time.monotonic() - start) * 1000))


class SpanProxy:
    """Tiny proxy that hides OTel types from application code."""

    __slots__ = ("span",)

    def __init__(self, span: Any) -> None:
        self.span = span

    def set_attribute(self, key: str, value: Any) -> None:
        self.span.set_attribute(key, _otel_value(value))

    def add_event(self, name: str, **attrs: Any) -> None:
        self.span.add_event(name, attributes=_otel_attrs(attrs))

    def set_status_error(self, message: str = "error") -> None:
        """Mark the active span as failed without raising."""
        self.span.set_status(trace.Status(trace.StatusCode.ERROR, message))
        self.span.record_exception(RuntimeError(message))


def _otel_value(v: Any) -> Any:
    return v if isinstance(v, (str, int, float, bool)) else str(v)


def _otel_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    return {k: _otel_value(v) for k, v in attrs.items()}


_SINGLETON: Tracer | None = None


def get_tracer() -> Tracer:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = Tracer()
    return _SINGLETON


def reset_tracer() -> None:
    global _SINGLETON
    _SINGLETON = None


__all__ = [
    "OTLP_ENDPOINT_ENV",
    "SpanProxy",
    "Tracer",
    "configure_tracing",
    "get_tracer",
    "reset_tracer",
]
