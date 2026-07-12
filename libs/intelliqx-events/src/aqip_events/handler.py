"""Event handler dataclass.

A thin Pydantic model around a callable so handlers can be carried in
the event registry, the in-memory bus's subscription list, etc.
``arbitrary_types_allowed`` is required because Pydantic doesn't
natively know how to validate callables.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict


class EventHandler(BaseModel):
    """A registered event handler.

    Attributes:
        name: Human-readable identifier; used in logs and tests.
        callback: The actual callable invoked on each event. Signature:
            ``(event: BaseModel) -> None`` or async variant.
        dlq: Optional dead-letter topic. If set, exceptions from
            ``callback`` are routed to this topic instead of being
            raised.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    callback: Callable[..., Any]
    dlq: str | None = None

    def handle(self, event: BaseModel) -> Any:
        """Invoke the wrapped callback synchronously.

        The in-memory bus awaits the result itself if it is a
        coroutine; this method only returns the value (or coroutine
        object) for the bus to inspect.
        """
        return self.callback(event)
