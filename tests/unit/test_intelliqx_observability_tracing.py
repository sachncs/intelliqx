"""Tests for the OTel tracer wrapper.

Covers: spans attach attributes, caught exceptions mark ERROR and
re-raise, nested spans inherit context, the optional OTLP/HTTP
exporter wires up only with an endpoint and never via console,
the new :meth:`SpanProxy.set_status_error` marks spans without
raising.
"""

from __future__ import annotations

import pytest
from intelliqx_observability import tracing
from intelliqx_observability.tracing import (
    OTLP_ENDPOINT_ENV,
    Tracer,
    configure_tracing,
    get_tracer,
    reset_tracer,
)


@pytest.mark.unit
def test_tracer_span_attaches_attributes() -> None:
    reset_tracer()
    t = Tracer()
    with t.span("outer", a=1) as s:
        s.set_attribute("b", 2)
        s.add_event("ev")


@pytest.mark.unit
def test_tracer_records_exception_and_reraises() -> None:
    reset_tracer()
    t = Tracer()
    with pytest.raises(RuntimeError), t.span("err") as s:
        s.set_attribute("k", "v")
        raise RuntimeError("boom")


@pytest.mark.unit
def test_set_status_error_marks_span_without_raising() -> None:
    """Compute's caught-exception path can mark the span ERROR."""
    reset_tracer()
    t = Tracer()
    with t.span("caught") as s:
        s.set_status_error("timeout")


@pytest.mark.unit
def test_nested_spans_inherit_context() -> None:
    reset_tracer()
    t = Tracer()
    with t.span("parent"), t.span("child"):
        pass


@pytest.mark.unit
def test_configure_tracing_without_endpoint_skips_otlp(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    class _Boom:
        def __init__(self, *a: object, **k: object) -> None:
            calls.append(a)
            raise AssertionError("OTLPSpanExporter must not be built without endpoint")

    monkeypatch.setattr(tracing, "OTLPSpanExporter", _Boom)
    monkeypatch.delenv(OTLP_ENDPOINT_ENV, raising=False)
    configure_tracing("svc")
    assert calls == []


@pytest.mark.unit
def test_configure_tracing_with_endpoint_wires_otlp(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Exporter:
        def __init__(self, *a: object, **k: object) -> None:
            captured["exporter_args"] = (a, k)

    class _Processor:
        def __init__(self, exporter: object) -> None:
            captured["processor"] = exporter

        def shutdown(self) -> None:
            pass

    monkeypatch.setattr(tracing, "OTLPSpanExporter", _Exporter)
    monkeypatch.setattr(tracing, "BatchSpanProcessor", _Processor)
    configure_tracing("svc", otlp_endpoint="http://collector:4318/v1/traces")
    assert captured["exporter_args"][1].get("endpoint") == "http://collector:4318/v1/traces"
    assert captured["processor"] is not None


@pytest.mark.unit
def test_no_console_exporter_in_source() -> None:
    """Guard against the deleted ConsoleSpanExporter returning."""
    with open(tracing.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "ConsoleSpanExporter" not in text
    assert "instrumentation.logging" not in text


@pytest.mark.unit
def test_get_tracer_is_singleton() -> None:
    reset_tracer()
    assert get_tracer() is get_tracer()
