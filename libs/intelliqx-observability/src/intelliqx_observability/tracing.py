"""Tracing for IntelliqX.

The platform uses OpenTelemetry for distributed tracing and provides a
thin Pythonic wrapper (:class:`Tracer` / :class:`_SpanProxy`) so agent
code never imports ``opentelemetry.*`` types directly. The wrapper
exposes only two operations on a span — ``set_attribute`` and
``add_event`` — which covers the vast majority of use cases.

Configuration is opt-in: by default the tracer is a no-op. Set
``INTELLIQX_OTEL=1`` to enable the console exporter, or call
:func:`configure_tracing` explicitly at startup.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)


def configure_tracing(service_name: str = "intelliqx", exporter: str = "console") -> None:
    """Configure OpenTelemetry tracing.

    Args:
        service_name: The ``service.name`` resource attribute attached
            to every span.
        exporter: One of ``"console"`` (default; prints spans to
            stdout), ``"none"`` (no exporter; spans are still
            recorded in memory but never serialised), or anything
            else (falls back to ``BatchSpanProcessor`` with a console
            exporter).
    """
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    if exporter == "console":
        # SimpleSpanProcessor flushes synchronously — ideal for tests
        # where we want to see spans immediately.
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    elif exporter == "none":
        pass
    else:
        # BatchSpanProcessor is the production default; spans are
        # buffered and flushed on a background thread.
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)


class Tracer:
    """Lightweight wrapper around an OpenTelemetry tracer.

    The wrapper hides the OTel span object behind a small proxy so
    agent code does not need to know the OTel API surface. The
    ``span`` context manager records the wall-clock duration in
    ``duration_ms`` for every span automatically.

    Example:
        >>> with tracer.span("agent.planner.run") as span:
        ...     span.set_attribute("tenant_id", "t1")
    """

    def __init__(self) -> None:
        self._tracer = trace.get_tracer("intelliqx")

    @contextmanager
    def span(self, name: str, **attrs: Any):
        """Open a span and yield a proxy for attribute/event access.

        Args:
            name: Span name. By convention, agent spans use
                ``"agent.<agent_name>.run"`` and runtime spans use
                ``"agent.<agent_name>.invoke"``.
            **attrs: Attributes attached to the span at open time.

        Yields:
            An :class:`_SpanProxy` for setting additional attributes
            and adding events.
        """
        span = self._tracer.start_span(name, attributes=_to_otel_attrs(attrs))
        start = time.monotonic()
        try:
            yield _SpanProxy(span)
        except Exception as e:
            # Mark the span as failed so backends render it red.
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            raise
        finally:
            # Always record the wall-clock duration, even on error.
            span.set_attribute("duration_ms", int((time.monotonic() - start) * 1000))
            span.end()


class _SpanProxy:
    """Proxy that lets callers set attributes/events without importing OTel.

    The proxy is intentionally tiny: a span has many more methods in
    OTel (``set_status``, ``add_link``, ``update_name`` …) but
    IntelliqX's needs are limited to attributes and events.
    """

    def __init__(self, span: Any) -> None:
        self._span = span

    def set_attribute(self, key: str, value: Any) -> None:
        """Attach a typed attribute to the span.

        Args:
            key: Attribute name (e.g. ``"tenant_id"``).
            value: Value; non-trivial types are stringified.
        """
        self._span.set_attribute(key, _to_otel_value(value))

    def add_event(self, name: str, **attrs: Any) -> None:
        """Add a timestamped event to the span.

        Args:
            name: Event name (e.g. ``"node_failed"``).
            **attrs: Event attributes.
        """
        self._span.add_event(name, attributes=_to_otel_attrs(attrs))


def _to_otel_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    """Coerce every attribute to an OTel-compatible primitive."""
    return {k: _to_otel_value(v) for k, v in attrs.items()}


def _to_otel_value(v: Any) -> Any:
    """Coerce a value to an OTel-allowed primitive (str|int|float|bool)."""
    if isinstance(v, (str, int, float, bool)):
        return v
    # Fallback: stringify complex values. Acceptable for tracing,
    # which is mostly observational.
    return str(v)


_SINGLETON: Tracer | None = None


def get_tracer() -> Tracer:
    """Return the process-wide :class:`Tracer`.

    If the ``INTELLIQX_OTEL`` env var is set, the underlying OTel SDK is
    configured on first call. Otherwise the tracer is a thin no-op
    wrapper that still records ``duration_ms`` on every span.
    """
    global _SINGLETON
    if _SINGLETON is None:
        if os.environ.get("INTELLIQX_OTEL") == "1":
            configure_tracing()
        _SINGLETON = Tracer()
    return _SINGLETON


def reset_tracer() -> None:
    """Clear the singleton tracer (for tests)."""
    global _SINGLETON
    _SINGLETON = None
