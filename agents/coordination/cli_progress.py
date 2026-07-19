"""CLI-side tqdm progress bar driven by the platform event bus.

This module renders ONE ``tqdm`` progress bar per orchestrated run by
subscribing a synchronous handler to ``plan.node.completed`` on the
in-process event bus. It deliberately:

* Sits at the CLI boundary only. The orchestrator and compute runtime
  stay unaware of the bar.
* Increments exactly once per terminal node result. ``PlanNodeStarted``
  never moves the counter.
* Closes the bar in ``finally`` even when the run is cancelled.
* Renders only when ``stderr.isatty()`` is true, never when
  ``INTELLIQX_PROGRESS`` is set to a falsy value, and never from inside
  the orchestrator module or the compute runtime.
* Routes Loguru log lines through ``tqdm.write`` while the bar is
  active so log output cannot corrupt the bar.

Forbidden: ``tqdm.asyncio.gather`` (we update the bar synchronously
from the bus callback, not from the orchestration coroutine).

Usage::

    from agents.coordination.cli_progress import CliProgressBar

    with CliProgressBar(plan=orchestrator_input):
        await orchestrator.invoke(request)
"""

from __future__ import annotations

import os
import sys
from typing import Any

from intelliqx_events.bus import get_event_bus
from intelliqx_observability.logging import configure_logging
from tqdm import tqdm  # type: ignore[import-untyped]  # tqdm has no py.typed marker

_PROGRESS_ENV = "INTELLIQX_PROGRESS"
_DISABLE_VALUES = frozenset({"0", "false", "no", "off", "n"})

__all__ = ["CliProgressBar", "is_progress_enabled"]


def is_progress_enabled(*, stderr: Any = None) -> bool:
    """Return True only when stderr is a TTY and the override allows it."""
    stream = sys.stderr if stderr is None else stderr
    if not stream.isatty():
        return False
    if _PROGRESS_ENV in os.environ:
        return os.environ[_PROGRESS_ENV].strip().lower() not in _DISABLE_VALUES
    return True


class CliProgressBar:
    """Single tqdm bar per run, driven by ``plan.node.completed`` events."""

    def __init__(
        self, plan: Any, *, description: str = "running", enabled: bool | None = None
    ) -> None:
        nodes = getattr(plan, "nodes", None) or []
        self.total = len(nodes) if hasattr(nodes, "__len__") else 0
        self._description = description
        self._forced = enabled
        self._bar: Any = None
        self._subscription_id: str | None = None
        self._retries = 0
        self._failed = 0
        self._blocked = 0

    @property
    def enabled(self) -> bool:
        """True iff a tqdm bar is currently active (entered & rendered)."""
        return self._bar is not None

    @property
    def counter(self) -> dict[str, int]:
        return {"retries": self._retries, "failed": self._failed, "blocked": self._blocked}

    @property
    def postfix(self) -> str:
        return f"retries={self._retries} " f"failed={self._failed} " f"blocked={self._blocked}"

    @property
    def progress(self) -> int:
        """How far the bar has advanced (for tests)."""
        return 0 if self._bar is None else int(self._bar.n)

    def _should_render(self) -> bool:
        if self.total <= 0:
            return False
        if self._forced is not None:
            return self._forced
        return is_progress_enabled()

    def on_completed(self, event: Any) -> None:
        """Bus callback: handle one terminal ``PlanNodeCompleted`` event.

        Increments the bar by one and updates the postfix counters.
        Safe to call when the bar is disabled (becomes a no-op).
        """
        if self._bar is None:
            return
        from agents.coordination.events import PlanNodeCompleted  # lazy: avoid cycle

        if not isinstance(event, PlanNodeCompleted):
            return
        attempts = getattr(event, "attempts", 0) or 0
        if attempts > 1:
            self._retries += attempts - 1
        outcome = getattr(event, "outcome", "")
        if outcome == "failed":
            self._failed += 1
        elif outcome == "blocked":
            self._blocked += 1
        self._bar.update(1)
        self._bar.set_postfix_str(self.postfix, refresh=False)

    def on_started(self, _event: Any) -> None:
        """Bus callback for ``PlanNodeStarted`` — must NOT move the counter."""

    def _install_log_sink(self) -> None:
        if self._bar is not None:
            configure_logging(sink=self._bar.write)

    def _restore_log_sink(self) -> None:
        configure_logging()

    def _install_bus_subscription(self) -> None:
        self._subscription_id = get_event_bus().subscribe("plan.node.completed", self.on_completed)

    def _remove_bus_subscription(self) -> None:
        if self._subscription_id is None:
            return
        try:
            get_event_bus().unsubscribe(self._subscription_id)
        finally:
            self._subscription_id = None

    def __enter__(self) -> CliProgressBar:
        if not self._should_render():
            return self
        self._bar = tqdm(
            total=self.total,
            desc=self._description,
            file=sys.stderr,
            dynamic_ncols=True,
            miniters=1,
            mininterval=0.05,
        )
        self._bar.set_postfix_str(self.postfix, refresh=False)
        self._install_log_sink()
        try:
            self._install_bus_subscription()
        except Exception:
            self._restore_log_sink()
            self._bar.close()
            self._bar = None
            raise
        return self

    def __exit__(self, *_exc: Any) -> None:
        try:
            self._remove_bus_subscription()
        finally:
            try:
                if self._bar is not None:
                    self._bar.close()
            finally:
                self._bar = None
                self._restore_log_sink()
