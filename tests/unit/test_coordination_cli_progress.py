"""Tests for the CLI-side tqdm progress bar wrapper."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from intelliqx_core.events import EventMetadata
from intelliqx_events.bus import get_event_bus
from intelliqx_observability.logging import configure_logging, get_logger, reset_logging

from agents.coordination.cli_progress import CliProgressBar, is_progress_enabled
from agents.coordination.events import PlanNodeCompleted, PlanNodeStarted


def _metadata() -> EventMetadata:
    return EventMetadata(tenant_id="t1", produced_by="test")


def _completed(
    node_id: str, *, outcome: str = "passed", attempts: int = 1, status: str = "ok"
) -> PlanNodeCompleted:
    return PlanNodeCompleted(
        metadata=_metadata(),
        plan_id="p1",
        node_id=node_id,
        agent="smoke",
        status=status,
        outcome=outcome,
        attempts=attempts,
    )


def _started(node_id: str) -> PlanNodeStarted:
    return PlanNodeStarted(metadata=_metadata(), plan_id="p1", node_id=node_id, agent="smoke")


class _FakeStream:
    def __init__(self, *, isatty: bool) -> None:
        self._isatty = isatty

    def isatty(self) -> bool:
        return self._isatty


class _FakeBar:
    """Records every method touched by ``CliProgressBar``.

    Mirrors only the API surface ``CliProgressBar`` actually uses
    (update, set_postfix_str, write, close).
    """

    def __init__(self, *, total: int) -> None:
        self.total = total
        self.n = 0
        self.updates: list[int] = []
        self.postfixes: list[str] = []
        self.writes: list[str] = []
        self.sink_writes: list[str] = []
        self.closed = False

    def update(self, n: int = 1) -> None:
        self.updates.append(n)
        self.n += n

    def set_postfix_str(self, postfix: str, **_kwargs: Any) -> None:
        self.postfixes.append(postfix)

    def write(self, line: str) -> None:
        self.writes.append(line)
        self.sink_writes.append(line)

    def close(self) -> None:
        self.closed = True


def _plan(node_ids: list[str]) -> Any:
    return type("Plan", (), {"nodes": node_ids})()


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_logging()
    yield
    reset_logging()


@pytest.fixture
def fake_tqdm(monkeypatch: pytest.MonkeyPatch) -> _FakeBar:
    """Replace tqdm in ``cli_progress`` with a recording fake."""

    fake = _FakeBar(total=0)
    monkeypatch.setattr("agents.coordination.cli_progress.tqdm", lambda *_a, **_kw: fake)
    return fake


@pytest.mark.unit
def test_is_progress_enabled_requires_tty_and_no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    assert is_progress_enabled(stderr=_FakeStream(isatty=True)) is True
    assert is_progress_enabled(stderr=_FakeStream(isatty=False)) is False
    monkeypatch.setenv("INTELLIQX_PROGRESS", "0")
    assert is_progress_enabled(stderr=_FakeStream(isatty=True)) is False
    monkeypatch.setenv("INTELLIQX_PROGRESS", "off")
    assert is_progress_enabled(stderr=_FakeStream(isatty=True)) is False
    monkeypatch.delenv("INTELLIQX_PROGRESS")
    assert is_progress_enabled(stderr=_FakeStream(isatty=True)) is True


@pytest.mark.unit
def test_bar_does_not_render_when_stderr_is_not_a_tty(
    monkeypatch: pytest.MonkeyPatch, fake_tqdm: _FakeBar
) -> None:
    monkeypatch.setattr("agents.coordination.cli_progress.sys.stderr", _FakeStream(isatty=False))
    bar = CliProgressBar(plan=_plan(["n1", "n2", "n3"]), enabled=None)
    with bar:
        assert bar.enabled is False
        assert bar.progress == 0
        bar.on_completed(_completed("n1"))
        bar.on_completed(_completed("n2"))
        assert bar.progress == 0
    assert bar.enabled is False
    assert fake_tqdm.closed is False


@pytest.mark.unit
def test_bar_does_not_render_when_progress_disabled(
    monkeypatch: pytest.MonkeyPatch, fake_tqdm: _FakeBar
) -> None:
    monkeypatch.setattr("agents.coordination.cli_progress.sys.stderr", _FakeStream(isatty=True))
    monkeypatch.setenv("INTELLIQX_PROGRESS", "0")
    bar = CliProgressBar(plan=_plan(["n1", "n2", "n3"]), enabled=None)
    with bar:
        assert bar.enabled is False
        for node_id in ("n1", "n2", "n3"):
            bar.on_completed(_completed(node_id))
        assert bar.progress == 0
        assert bar.postfix == "retries=0 failed=0 blocked=0"
    assert bar.enabled is False
    assert fake_tqdm.closed is False


@pytest.mark.unit
def test_bar_callback_increments_exactly_once_per_terminal_event(
    monkeypatch: pytest.MonkeyPatch, fake_tqdm: _FakeBar
) -> None:
    monkeypatch.setattr("agents.coordination.cli_progress.sys.stderr", _FakeStream(isatty=True))
    monkeypatch.setenv("INTELLIQX_PROGRESS", "1")
    nodes = ["n1", "n2", "n3"]
    fake_tqdm.total = len(nodes)
    bar = CliProgressBar(plan=_plan(nodes), enabled=None)
    with bar:
        assert bar.enabled is True
        assert bar.total == 3
        for node_id in nodes:
            bar.on_completed(_completed(node_id))
        assert fake_tqdm.updates == [1, 1, 1]
        assert fake_tqdm.n == 3
        assert bar.progress == 3
    assert fake_tqdm.closed is True
    assert bar.enabled is False


@pytest.mark.unit
def test_bar_postfix_counts_failures_blocked_and_retries(
    monkeypatch: pytest.MonkeyPatch, fake_tqdm: _FakeBar
) -> None:
    monkeypatch.setattr("agents.coordination.cli_progress.sys.stderr", _FakeStream(isatty=True))
    monkeypatch.setenv("INTELLIQX_PROGRESS", "1")
    fake_tqdm.total = 4
    bar = CliProgressBar(plan=_plan(["a", "b", "c", "d"]), enabled=None)
    with bar:
        bar.on_completed(_completed("a"))
        bar.on_completed(_completed("b", outcome="failed", attempts=3))
        bar.on_completed(_completed("c", outcome="blocked"))
        bar.on_completed(_completed("d", outcome="passed", attempts=2))
    assert bar.counter == {"retries": 3, "failed": 1, "blocked": 1}
    postfixes = [p for p in fake_tqdm.postfixes if p.startswith("retries=")]
    # Order of postfixes: initial, after each on_completed call.
    assert postfixes == [
        "retries=0 failed=0 blocked=0",  # initial
        "retries=0 failed=0 blocked=0",  # after "a" (passed, attempts=1)
        "retries=2 failed=1 blocked=0",  # after "b" (failed, attempts=3)
        "retries=2 failed=1 blocked=1",  # after "c" (blocked)
        "retries=3 failed=1 blocked=1",  # after "d" (passed, attempts=2)
    ]


@pytest.mark.unit
def test_bar_does_not_count_retries_for_first_attempt(
    monkeypatch: pytest.MonkeyPatch, fake_tqdm: _FakeBar
) -> None:
    monkeypatch.setattr("agents.coordination.cli_progress.sys.stderr", _FakeStream(isatty=True))
    monkeypatch.setenv("INTELLIQX_PROGRESS", "1")
    fake_tqdm.total = 2
    bar = CliProgressBar(plan=_plan(["a", "b"]), enabled=None)
    with bar:
        bar.on_completed(_completed("a", attempts=1))
        bar.on_completed(_completed("b", attempts=1, outcome="passed"))
    assert bar.counter == {"retries": 0, "failed": 0, "blocked": 0}


@pytest.mark.unit
def test_bar_ignores_plan_node_started(
    monkeypatch: pytest.MonkeyPatch, fake_tqdm: _FakeBar
) -> None:
    monkeypatch.setattr("agents.coordination.cli_progress.sys.stderr", _FakeStream(isatty=True))
    monkeypatch.setenv("INTELLIQX_PROGRESS", "1")
    fake_tqdm.total = 3
    bar = CliProgressBar(plan=_plan(["n1", "n2", "n3"]), enabled=None)
    with bar:
        for node_id in ("n1", "n2", "n3"):
            bar.on_started(_started(node_id))
        for node_id in ("n1", "n2", "n3"):
            bar.on_completed(_completed(node_id))
        assert fake_tqdm.n == 3


@pytest.mark.unit
def test_loguru_sink_routes_through_tqdm_write_when_bar_active(
    monkeypatch: pytest.MonkeyPatch, fake_tqdm: _FakeBar
) -> None:
    monkeypatch.setattr("agents.coordination.cli_progress.sys.stderr", _FakeStream(isatty=True))
    monkeypatch.setenv("INTELLIQX_PROGRESS", "1")
    fake_tqdm.total = 1
    bar = CliProgressBar(plan=_plan(["n1"]), enabled=None)
    captured_sinks: list[Any] = []
    real_configure = configure_logging

    def spy_configure(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("sink") is not None:
            captured_sinks.append(kwargs["sink"])
        return real_configure(*args, **kwargs)

    monkeypatch.setattr("agents.coordination.cli_progress.configure_logging", spy_configure)
    with bar:
        get_logger("demo").info("hello world")
    assert fake_tqdm.sink_writes, "Loguru output did not reach the bar's write()"
    assert (
        fake_tqdm.write in captured_sinks
    ), "Loguru sink was not set to bar.write while bar is active"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bar_closes_in_finally_on_cancellation(
    monkeypatch: pytest.MonkeyPatch, fake_tqdm: _FakeBar
) -> None:
    monkeypatch.setattr("agents.coordination.cli_progress.sys.stderr", _FakeStream(isatty=True))
    monkeypatch.setenv("INTELLIQX_PROGRESS", "1")
    fake_tqdm.total = 3
    bar = CliProgressBar(plan=_plan(["n1", "n2", "n3"]), enabled=None)
    bus = get_event_bus()
    bus_completed: list[str] = []

    def on_completed(event: PlanNodeCompleted) -> None:
        bus_completed.append(event.node_id)

    sub_id = bus.subscribe("plan.node.completed", on_completed)
    try:
        bar.__enter__()
        try:
            assert bar.enabled is True
            await bus.publish("plan.node.completed", _completed("n1"))
            assert bar.progress == 1
            raise asyncio.CancelledError
        finally:
            bar.__exit__(asyncio.CancelledError, None, None)
    except asyncio.CancelledError:
        pass
    assert fake_tqdm.closed is True
    assert bar.enabled is False
    assert bus_completed == ["n1"]
    bus.unsubscribe(sub_id)
