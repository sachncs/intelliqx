"""In-process metrics for AQIP.

The platform exposes three primitive metric types — counter, gauge, and
histogram — plus a :class:`MetricsRegistry` that lazily creates and
caches them by name. The implementation is intentionally
**thread-safe but not multiprocess-safe**: counters, gauges, and
histograms live in process memory. For multi-process aggregation, use
a Prometheus client or OpenTelemetry exporter in production (the
:class:`MetricsRegistry` is the in-process reference for tests).

All primitives use a small ``threading.Lock`` per metric to avoid
contention while keeping the public API simple. Lock granularity is
per-metric, not per-registry.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from contextlib import contextmanager
from typing import Any


class Counter:
    """A monotonically increasing counter.

    A counter accumulates ``inc`` calls. Use counters for things like
    ``agent_invocations_total``, ``plan_nodes_completed``, etc.

    The label set is encoded as a sorted tuple of ``(name, value)``
    pairs to make label dictionaries hashable for the internal
    ``values`` map.
    """

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        # label tuple -> running total
        self._values: dict[tuple[tuple[str, str], ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, **labels: Any) -> None:
        """Add ``amount`` (default 1.0) to the counter.

        Args:
            amount: Increment size; must be non-negative.
            **labels: Optional label dimensions (``tenant="t1"`` etc.).
        """
        # Sorting ensures (k=v) pairs hash consistently regardless of
        # insertion order, so ``inc(tenant="t1")`` and
        # ``inc(tenant="t1", other="x")`` produce stable keys.
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] += amount

    def value(self, **labels: Any) -> float:
        """Return the current counter value for the given label set.

        Args:
            **labels: Must match exactly the labels used on ``inc``.

        Returns:
            The current total, or 0.0 if no observations have been
            recorded for that label set.
        """
        key = tuple(sorted(labels.items()))
        return self._values.get(key, 0.0)

    def snapshot(self) -> dict[str, float]:
        """Return a flat ``{label_key: value}`` dict.

        Each entry's key is a Prometheus-style exposition line
        (``"agent_invocations_total{tenant=t1}"``).
        """
        with self._lock:
            return {
                f"{self.name}{{{','.join(f'{k}={v}' for k, v in k)}}}": v
                for k, v in self._values.items()
            }


class Gauge:
    """A gauge metric (point-in-time value).

    Unlike :class:`Counter`, a gauge is set, not accumulated. Use
    gauges for things like queue depth, current memory, or any
    "current state" measurement.
    """

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._values: dict[tuple[tuple[str, str], ...], float] = {}
        self._lock = threading.Lock()

    def set(self, value: float, **labels: Any) -> None:
        """Set the gauge to ``value`` for the given label set.

        Args:
            value: New gauge value.
            **labels: Optional label dimensions.
        """
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = value

    def value(self, **labels: Any) -> float:
        """Return the current gauge value for the given label set.

        Returns 0.0 if the gauge has not been set.
        """
        key = tuple(sorted(labels.items()))
        return self._values.get(key, 0.0)

    def snapshot(self) -> dict[str, float]:
        """Return a flat ``{label_key: value}`` dict (Prometheus-style)."""
        with self._lock:
            return {
                f"{self.name}{{{','.join(f'{k}={v}' for k, v in k)}}}": v
                for k, v in self._values.items()
            }


class Histogram:
    """A histogram metric (count, sum, min, max, p50, p95, p99).

    Observations are kept in a per-label-set list and percentiles are
    computed on demand at snapshot time. Memory grows linearly with
    observation count; the cost is acceptable for the small
    per-process histograms AQIP tracks (agent latencies, token
    counts). For high-cardinality histograms, replace with
    OpenTelemetry's t-digest in production.

    Complexity: ``observe`` is O(1) amortised; ``snapshot`` is
    O(n log n) per label set due to the percentile sort.
    """

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._samples: dict[tuple[tuple[str, str], ...], list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def observe(self, value: float, **labels: Any) -> None:
        """Record a single observation.

        Args:
            value: Sample value.
            **labels: Optional label dimensions.
        """
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._samples[key].append(value)

    @contextmanager
    def time(self, **labels: Any):
        """Time a block of code and observe its duration in milliseconds.

        Use as ``with histogram.time(agent="x"): ...``.
        """
        import time

        start = time.monotonic()
        yield
        self.observe((time.monotonic() - start) * 1000.0, **labels)

    def snapshot(self) -> dict[str, dict[str, float]]:
        """Return a flat ``{label_key: {stat: value}}`` dict.

        For each label set we publish ``count``, ``sum``, ``min``,
        ``max``, ``p50``, ``p95``, ``p99``. The percentile
        computation is the standard nearest-rank method.
        """
        out: dict[str, dict[str, float]] = {}
        with self._lock:
            for k, samples in self._samples.items():
                if not samples:
                    continue
                sorted_s = sorted(samples)
                n = len(sorted_s)

                # Default-arg trick: capture sorted_s and n from the
                # enclosing scope so the inner function doesn't
                # accidentally pick up loop variables (which would
                # change between iterations under PEP 227).
                def pct(p: float, sorted_s: list[float] = sorted_s, n: int = n) -> float:
                    # Nearest-rank percentile; clamp to last index to
                    # avoid out-of-range when p == 1.0.
                    i = min(n - 1, int(p * n))
                    return sorted_s[i]

                out[f"{self.name}{{{','.join(f'{kk}={vv}' for kk, vv in k)}}}"] = {
                    "count": float(n),
                    "sum": sum(samples),
                    "min": min(samples),
                    "max": max(samples),
                    "p50": pct(0.50),
                    "p95": pct(0.95),
                    "p99": pct(0.99),
                }
        return out


class MetricsRegistry:
    """Process-wide registry of named metrics.

    Metrics are created lazily on first access. The registry holds
    only weak references to nothing — metrics live for the process
    lifetime. Tests that need a clean world call :func:`reset_metrics`
    (provided by this module) to clear the registry.
    """

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._lock = threading.Lock()

    def counter(self, name: str, description: str = "") -> Counter:
        """Get or create a counter by name.

        Args:
            name: Counter name.
            description: Optional human-readable description.
        """
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description)
            return self._counters[name]

    def gauge(self, name: str, description: str = "") -> Gauge:
        """Get or create a gauge by name."""
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, description)
            return self._gauges[name]

    def histogram(self, name: str, description: str = "") -> Histogram:
        """Get or create a histogram by name."""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, description)
            return self._histograms[name]

    def snapshot(self) -> dict[str, Any]:
        """Return the full registry snapshot.

        Returns:
            A dict with three keys — ``"counters"``, ``"gauges"``,
            ``"histograms"`` — each mapping metric name to its
            per-label-set dict.
        """
        return {
            "counters": {n: c.snapshot() for n, c in self._counters.items()},
            "gauges": {n: g.snapshot() for n, g in self._gauges.items()},
            "histograms": {n: h.snapshot() for n, h in self._histograms.items()},
        }

    def reset(self) -> None:
        """Remove every metric from the registry.

        Tests call this between cases to keep the global registry
        clean. Production code should not call it.
        """
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


_SINGLETON: MetricsRegistry | None = None


def get_metrics() -> MetricsRegistry:
    """Return the process-wide :class:`MetricsRegistry`."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = MetricsRegistry()
    return _SINGLETON


def reset_metrics() -> None:
    """Clear the singleton registry (for tests)."""
    global _SINGLETON
    if _SINGLETON is not None:
        _SINGLETON.reset()
    _SINGLETON = None
