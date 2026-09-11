"""Tests for intelliqx-observability."""

import pytest
from intelliqx_observability.logging import configure_logging, get_logger, reset_logging
from intelliqx_observability.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    get_metrics,
    render_prometheus,
    reset_metrics,
)
from intelliqx_observability.tracing import Tracer, get_tracer, reset_tracer


@pytest.mark.unit
def test_logger_smoke():
    reset_logging()
    configure_logging(level="INFO", json_logs=True, enqueue=False)
    log = get_logger("test")
    assert log is not None
    log.info("hello", k=1)
    reset_logging()


@pytest.mark.unit
def test_counter_inc():
    c = Counter("c", "d")
    c.inc()
    c.inc(amount=5)
    c.inc(tenant="t1")
    assert c.value() == 6.0
    assert c.value(tenant="t1") == 1.0


@pytest.mark.unit
def test_gauge_set():
    g = Gauge("g", "d")
    g.set(10.0)
    g.set(20.0, tenant="t1")
    assert g.value() == 10.0
    assert g.value(tenant="t1") == 20.0


@pytest.mark.unit
def test_histogram_observe():
    h = Histogram("h", "d")
    for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
        h.observe(float(v))
    snap = h.snapshot()
    assert "h{}" in snap
    assert snap["h{}"]["count"] == 10
    assert snap["h{}"]["min"] == 1.0
    assert snap["h{}"]["max"] == 10.0


@pytest.mark.unit
def test_metrics_registry():
    r = MetricsRegistry()
    c = r.counter("c1")
    g = r.gauge("g1")
    h = r.histogram("h1")
    c.inc()
    g.set(1.0)
    h.observe(2.0)
    snap = r.snapshot()
    assert "c1" in snap["counters"]
    assert "g1" in snap["gauges"]
    assert "h1" in snap["histograms"]


@pytest.mark.unit
def test_tracer_span():
    reset_tracer()
    t = Tracer()
    with t.span("test.span") as s:
        s.set_attribute("k", "v")
        s.add_event("ev")


@pytest.mark.unit
def test_tracer_records_exception():
    reset_tracer()
    t = Tracer()
    with pytest.raises(RuntimeError), t.span("err.span") as s:
        s.set_attribute("k", "v")
        raise RuntimeError("boom")


@pytest.mark.unit
def test_get_tracer_singleton():
    reset_tracer()
    a = get_tracer()
    b = get_tracer()
    assert a is b


@pytest.mark.unit
def test_render_prometheus_emits_counter_gauge_histogram():
    reset_metrics()
    registry = get_metrics()
    registry.counter("agent_invocations_total", "test").inc(amount=3, agent="smoke")
    registry.gauge("queue_depth", "test").set(7)
    registry.histogram("agent_latency_ms", "test").observe(12.0, agent="smoke")
    registry.histogram("agent_latency_ms", "test").observe(48.0, agent="smoke")
    output = render_prometheus()
    assert "# TYPE agent_invocations_total counter" in output
    assert "agent_invocations_total{agent=smoke}" in output
    assert "# TYPE queue_depth gauge" in output
    assert "queue_depth{} 7" in output
    assert "# TYPE agent_latency_ms summary" in output
    assert "agent_latency_ms_count" in output
    assert "agent_latency_ms_sum" in output
    assert "agent_latency_ms_p95" in output
    reset_metrics()
